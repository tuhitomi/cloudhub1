import {t as tr} from './i18n.js';
// Passwords go directly over HTTPS to Cognito; session.js owns token storage.
export async function cognitoRequest(cfg, action, body){
  if(!cfg.configured || !/^[a-z]{2}-[a-z]+-\d$/.test(cfg.region) || !/^[a-z0-9]{1,128}$/.test(cfg.clientId))throw Error(tr("ui.d80e96ab4c54"));
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),15000);
  try{
    const response=await fetch('https://cognito-idp.'+cfg.region+'.amazonaws.com/',{method:'POST',headers:{'Content-Type':'application/x-amz-json-1.1','X-Amz-Target':'AWSCognitoIdentityProviderService.'+action},body:JSON.stringify(body),signal:controller.signal});
    const data=await response.json();
    if(!response.ok){
      const code=(data.__type||'').split('#').pop();
      const messages={NotAuthorizedException:tr("ui.2f6b3b4383bd"),UserNotFoundException:tr("ui.2f6b3b4383bd"),InvalidPasswordException:tr("ui.5cc0554ee583"),PasswordResetRequiredException:tr("ui.a9186c39ec99"),UserNotConfirmedException:tr("ui.9877953b6bf9"),CodeMismatchException:tr("ui.9f8b5ff33ebb"),ExpiredCodeException:tr("ui.70be974ec9fd"),TooManyRequestsException:tr("ui.fc7a4ef7062c"),InvalidParameterException:tr("ui.c2b7a1e25716")};
      const extra={UsernameExistsException:tr("ui.b68aba9164b7"),LimitExceededException:tr("ui.35b5ac22752d"),CodeDeliveryFailureException:tr("ui.99d73c8e50ef")};
      const error=Error(messages[code]||extra[code]||tr("ui.cd6854a0e75f"));error.code=code;throw error;
    }
    return data;
  }catch(error){if(error.name==='AbortError'||error instanceof TypeError)throw Error(tr("ui.9ce8381d1166"));throw error;}
  finally{clearTimeout(timeout);}
}

export function claims(token){
  const payload=token.split('.')[1]?.replace(/-/g,'+').replace(/_/g,'/');
  if(!payload)throw Error(tr("ui.55a234a5771e"));
  return JSON.parse(atob(payload));
}

export function normalizedTokens(cfg, result, previous){
  const value=result.AuthenticationResult;
  if(!value?.AccessToken)throw Object.assign(Error(tr("ui.049b15c2ab21")),{code:'SESSION_IDENTITY'});
  let after;try{after=claims(value.AccessToken);}catch{throw Object.assign(Error(tr("ui.55a234a5771e")),{code:'SESSION_IDENTITY'});}
  if(after.token_use!=='access'||after.client_id!==cfg.clientId||!after.sub||!Number.isFinite(Number(after.exp))||Number(after.exp)*1000<=Date.now())throw Object.assign(Error(tr("ui.55a234a5771e")),{code:'SESSION_IDENTITY'});
  if(previous){const before=claims(previous);if(before.iss!==after.iss||before.sub!==after.sub)throw Object.assign(Error(tr("ui.8770e50439ee")),{code:'SESSION_IDENTITY'});}
  return {access_token:value.AccessToken,refresh_token:value.RefreshToken||null};
}

export async function refreshCognito(cfg, token, previous){
  return normalizedTokens(cfg,await cognitoRequest(cfg,'InitiateAuth',{AuthFlow:'REFRESH_TOKEN_AUTH',ClientId:cfg.clientId,AuthParameters:{REFRESH_TOKEN:token}}),previous);
}

export function createCognitoAuth({cfg,onAuthenticated,onUnconfirmed=()=>{},onSignup=()=>{}}){
  const $=selector=>document.querySelector(selector);
  const signupSwitch=$('#login-to-signup');
  let challenge=null,username='',requesting=false;
  function clear(){challenge=null;username='';if(signupSwitch)signupSwitch.disabled=false;$('#login-form').reset();$('#login-new-fields').hidden=true;$('#login-code-fields').hidden=true;$('#login-password-fields').hidden=false;$('#login-password').required=true;$('#login-new-password').required=false;$('#login-code').required=false;$('#login-email').readOnly=false;$('#login-submit').textContent=tr("ui.9a402bdfdea7");}
  function cancel(){if(requesting)return;clear();$('#login-dialog').close();}
  function open(email=''){if(!cfg.configured)throw Error(tr("ui.d80e96ab4c54"));clear();$('#login-email').value=typeof email==='string'?email:'';$('#login-notice').textContent='';$('#login-dialog').showModal();$('#login-email').focus();}
  if(signupSwitch)signupSwitch.onclick=()=>{if(requesting||challenge)return;const email=$('#login-email').value;clear();$('#login-dialog').close();onSignup(email);};
  $('#login-close').onclick=cancel;
  $('#login-dialog').addEventListener('cancel',event=>{event.preventDefault();cancel();});
  $('#login-form').onsubmit=async event=>{
    event.preventDefault();if(requesting)return;requesting=true;if(signupSwitch)signupSwitch.disabled=true;$('#login-submit').disabled=true;$('#login-close').disabled=true;$('#login-notice').textContent=tr("ui.f534817b1194");
    try{
      let response;
      if(!challenge){username=$('#login-email').value.trim().toLowerCase();response=await cognitoRequest(cfg,'InitiateAuth',{ClientId:cfg.clientId,AuthFlow:'USER_PASSWORD_AUTH',AuthParameters:{USERNAME:username,PASSWORD:$('#login-password').value}});}
      else{
        const values={USERNAME:username};
        if(challenge.ChallengeName==='NEW_PASSWORD_REQUIRED')values.NEW_PASSWORD=$('#login-new-password').value;
        else{const keys={SMS_MFA:'SMS_MFA_CODE',SOFTWARE_TOKEN_MFA:'SOFTWARE_TOKEN_MFA_CODE',EMAIL_OTP:'EMAIL_OTP_CODE',SMS_OTP:'SMS_OTP_CODE'};values[keys[challenge.ChallengeName]]=$('#login-code').value.trim();}
        response=await cognitoRequest(cfg,'RespondToAuthChallenge',{ClientId:cfg.clientId,ChallengeName:challenge.ChallengeName,Session:challenge.Session,ChallengeResponses:values});
      }
      if(response.AuthenticationResult){const tokens=normalizedTokens(cfg,response),remember=$('#login-remember')?.checked!==false;clear();$('#login-dialog').close();await onAuthenticated(tokens,{remember});return;}
      if(!response.Session||!['NEW_PASSWORD_REQUIRED','SMS_MFA','SOFTWARE_TOKEN_MFA','EMAIL_OTP','SMS_OTP'].includes(response.ChallengeName))throw Error(tr("ui.8a7027b9b6d8"));
      if(response.ChallengeName==='NEW_PASSWORD_REQUIRED'&&JSON.parse(response.ChallengeParameters?.requiredAttributes||'[]').length)throw Error(tr("ui.77fe4a961cad"));
      challenge=response;username=response.ChallengeParameters?.USER_ID_FOR_SRP||username;
      const password=challenge.ChallengeName==='NEW_PASSWORD_REQUIRED';$('#login-password-fields').hidden=true;$('#login-password').required=false;$('#login-new-fields').hidden=!password;$('#login-new-password').required=password;$('#login-code-fields').hidden=password;$('#login-code').required=!password;$('#login-email').readOnly=true;
      $('#login-submit').textContent=password?tr("ui.16281243af6b"):tr("ui.ad988d2b7895");$('#login-notice').textContent=password?tr("ui.ec57e2977504"):tr("ui.155362c73fc8");
    }catch(error){$('#login-notice').textContent=error.message;if(error.code==='UserNotConfirmedException'){const pending=username;clear();$('#login-dialog').close();onUnconfirmed(pending);}}
    finally{$('#login-password').value='';$('#login-new-password').value='';$('#login-code').value='';requesting=false;$('#login-submit').disabled=false;$('#login-close').disabled=false;if(signupSwitch)signupSwitch.disabled=!!challenge;}
  };
  return {open};
}

export function createRegistration({cfg,onConfirmed,onSignin=()=>{}}){
  const $=s=>document.querySelector(s);
  let email='',busy=false,resendAt=0;
  function openVerification(value){email=value.trim().toLowerCase();$('#verification-email').value=email;$('#verification-code').value='';$('#verification-notice').textContent=tr("ui.4ad2c6bb3006");$('#verification-dialog').showModal();}
  function open(value=''){if(!cfg.configured)throw Error(tr("ui.e1efb9f072ba"));$('#signup-form').reset();$('#signup-email').value=typeof value==='string'?value:'';$('#signup-notice').textContent='';$('#signup-dialog').showModal();$('#signup-email').focus();}
  function lock(value){busy=value;for(const id of ['signup-submit','signup-close','signup-to-login','verification-submit','verification-close','verification-resend']){const control=$('#'+id);if(control)control.disabled=value;}}
  const signinSwitch=$('#signup-to-login');if(signinSwitch)signinSwitch.onclick=()=>{if(busy)return;const email=$('#signup-email').value;$('#signup-form').reset();$('#signup-dialog').close();onSignin(email);};
  function closeSignup(){if(busy)return;$('#signup-form').reset();$('#signup-dialog').close();}
  function closeVerification(){if(busy)return;$('#verification-code').value='';$('#verification-dialog').close();}
  $('#signup-close').onclick=closeSignup;$('#verification-close').onclick=closeVerification;
  $('#signup-dialog').addEventListener('cancel',e=>{e.preventDefault();closeSignup();});
  $('#verification-dialog').addEventListener('cancel',e=>{e.preventDefault();closeVerification();});
  $('#signup-form').onsubmit=async e=>{
    e.preventDefault();if(busy)return;lock(true);$('#signup-notice').textContent=tr("ui.55e36d9b98c3");
    try{
      if($('#signup-password').value!==$('#signup-password-confirm').value)throw Error(tr("ui.5fa78a632a4e"));
      email=$('#signup-email').value.trim().toLowerCase();
      const result=await cognitoRequest(cfg,'SignUp',{ClientId:cfg.clientId,Username:email,Password:$('#signup-password').value,UserAttributes:[{Name:'email',Value:email}]});
      if(result.UserConfirmed)throw Error(tr("ui.5a537338b862"));
      $('#signup-dialog').close();resendAt=Date.now()+60000;openVerification(email);
    }catch(error){$('#signup-notice').textContent=error.message;}
    finally{$('#signup-password').value='';$('#signup-password-confirm').value='';lock(false);}
  };
  $('#verification-form').onsubmit=async e=>{
    e.preventDefault();if(busy)return;lock(true);$('#verification-notice').textContent=tr("ui.f534817b1194");
    try{email=$('#verification-email').value.trim().toLowerCase();await cognitoRequest(cfg,'ConfirmSignUp',{ClientId:cfg.clientId,Username:email,ConfirmationCode:$('#verification-code').value.trim()});$('#verification-dialog').close();onConfirmed(email);}
    catch(error){$('#verification-notice').textContent=error.message;}
    finally{$('#verification-code').value='';lock(false);}
  };
  $('#verification-resend').onclick=async()=>{
    if(busy)return;if(Date.now()<resendAt){$('#verification-notice').textContent=tr("ui.9400f3b7eaf7")+Math.ceil((resendAt-Date.now())/1000)+tr("ui.4a2e4d838da2");return;}
    lock(true);
    try{email=$('#verification-email').value.trim().toLowerCase();await cognitoRequest(cfg,'ResendConfirmationCode',{ClientId:cfg.clientId,Username:email});resendAt=Date.now()+60000;$('#verification-notice').textContent=tr("ui.f414a3158795");}
    catch(error){$('#verification-notice').textContent=error.message;}finally{lock(false);}
  };
  return {open,openVerification};
}
