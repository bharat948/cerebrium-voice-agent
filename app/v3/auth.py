"""Google owner login via OIDC. The Google account subject, not email, grants owner access."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from app.config import get_settings

router=APIRouter()

def google_oauth():
    from authlib.integrations.starlette_client import OAuth
    s=get_settings()
    oauth=OAuth()
    oauth.register(name='google',client_id=s.google_client_id,client_secret=s.google_client_secret,
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope':'openid email profile'})
    return oauth.google

@router.get('/auth/google/login')
async def login(request:Request):
    s=get_settings()
    if s.auth_mode!='google' or not (s.google_client_id and s.google_client_secret and s.google_owner_sub):
        raise HTTPException(503,'Google authentication not configured')
    return await google_oauth().authorize_redirect(request,s.base_url+'/auth/google/callback')

@router.get('/auth/google/callback')
async def callback(request:Request):
    token=await google_oauth().authorize_access_token(request)
    user=token.get('userinfo')
    if not user or user.get('sub')!=get_settings().google_owner_sub:
        raise HTTPException(403,'This Google account is not the workspace owner')
    request.session['owner_sub']=user['sub']
    return RedirectResponse('/',status_code=303)

@router.post('/auth/logout')
async def logout(request:Request):
    request.session.clear()
    return {'signed_out':True}

@router.get('/auth/me')
async def me(request:Request):
    s=get_settings()
    return {'mode':s.auth_mode,'authenticated':s.auth_mode=='google' and request.session.get('owner_sub')==s.google_owner_sub}
