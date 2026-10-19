package io.github.try2love.codexbridge;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import org.json.JSONObject;

/** Device-only encrypted copy of a server-revocable native session. */
final class DeviceBinding {
 private static final String ALIAS="codex-bridge-device-binding-v1";
 static final class Credential {
  final String name,token;
  Credential(String name,String token){this.name=name;this.token=token;}
  String cookie(){return name+"="+token;}
 }
 static boolean name(String value){return value!=null&&value.matches("codex_mobile_session_[a-f0-9]{24}|codex_mobile_session");}
 static SharedPreferences prefs(Context context){return context.getSharedPreferences("bridge-bindings",0);}
 private static SecretKey key()throws Exception {
  KeyStore store=KeyStore.getInstance("AndroidKeyStore");store.load(null);
  SecretKey key=(SecretKey)store.getKey(ALIAS,null);
  if(key!=null)return key;
  KeyGenerator generator=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
  generator.init(new KeyGenParameterSpec.Builder(ALIAS,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT)
   .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setKeySize(256).build());
  return generator.generateKey();
 }
 static void save(Context context,String origin,String name,String token)throws Exception {
  if(!GatewayURL.origin(origin).equals(origin)||!name(name)||token==null||!token.matches("[A-Za-z0-9_-]{32,128}"))return;
  Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,key());
  byte[] payload=new JSONObject().put("name",name).put("token",token).toString().getBytes(StandardCharsets.UTF_8);
  byte[] iv=cipher.getIV(),encrypted=cipher.doFinal(payload),combined=new byte[iv.length+encrypted.length];
  System.arraycopy(iv,0,combined,0,iv.length);System.arraycopy(encrypted,0,combined,iv.length,encrypted.length);
  prefs(context).edit().putString(origin,Base64.encodeToString(combined,Base64.NO_WRAP)).apply();
 }
 static Credential load(Context context,String origin){
  String encoded=prefs(context).getString(origin,null);if(encoded==null)return null;
  try{
   byte[] bytes=Base64.decode(encoded,Base64.NO_WRAP);if(bytes.length<29||bytes.length>1024)return null;
   Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.DECRYPT_MODE,key(),new GCMParameterSpec(128,bytes,0,12));
   JSONObject value=new JSONObject(new String(cipher.doFinal(bytes,12,bytes.length-12),StandardCharsets.UTF_8));
   String name=value.getString("name"),token=value.getString("token");
   return name(name)&&token.matches("[A-Za-z0-9_-]{32,128}")?new Credential(name,token):null;
  }catch(Exception invalid){return null;}
 }
 static void clear(Context context,String origin){prefs(context).edit().remove(origin).apply();}
 /** Returns null for a network/transport error, false for server-confirmed invalidity. */
 static Boolean verify(String origin,Credential credential){
  HttpURLConnection connection=null;
  try{
   if(!GatewayURL.origin(origin).equals(origin))return false;
   connection=TailnetHttp.open(new URL(origin+"/api/auth"));
   connection.setInstanceFollowRedirects(false);connection.setConnectTimeout(4000);connection.setReadTimeout(4000);
   connection.setRequestProperty("Cookie",credential.cookie());connection.setRequestProperty("Origin",GatewayURL.httpOrigin(origin));connection.setRequestProperty("User-Agent",EventClient.USER_AGENT);
   if(connection.getResponseCode()!=200||!GatewayURL.sameOrigin(connection.getURL().toString(),origin))return null;
   ByteArrayOutputStream out=new ByteArrayOutputStream();try(InputStream in=connection.getInputStream()){
    byte[] bytes=new byte[4096];int n;while((n=in.read(bytes))!=-1){if(out.size()+n>65536)return null;out.write(bytes,0,n);}
   }
   JSONObject auth=new JSONObject(out.toString("UTF-8"));
   if(!auth.optBoolean("authenticated"))return false;
   String returned=auth.optString("cookieName","");
   return returned.isEmpty()?credential.name.equals("codex_mobile_session"):returned.equals(credential.name);
  }catch(Exception unavailable){return null;}finally{if(connection!=null)connection.disconnect();}
 }
}
