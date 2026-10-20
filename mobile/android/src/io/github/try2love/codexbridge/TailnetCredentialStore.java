package io.github.try2love.codexbridge;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Optional pre-authentication key encrypted by Android Keystore. */
final class TailnetCredentialStore {
 private static final String PREF="bridge-tailnet";
 private static final String KEY="authKey";
 private static final String ALIAS="codex-bridge-tailnet-auth-v1";
 private static final String AUTH_PREFIX="tskey-auth-";

 private TailnetCredentialStore(){}

 private static SecretKey key()throws Exception {
  KeyStore store=KeyStore.getInstance("AndroidKeyStore");store.load(null);
  SecretKey existing=(SecretKey)store.getKey(ALIAS,null);
  if(existing!=null)return existing;
  KeyGenerator generator=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
  generator.init(new KeyGenParameterSpec.Builder(ALIAS,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT)
   .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).setKeySize(256).build());
  return generator.generateKey();
 }

 static boolean valid(String value){
  return value!=null&&value.length()>=20&&value.length()<=16384&&value.startsWith(AUTH_PREFIX)&&value.matches("tskey-auth-[A-Za-z0-9_-]+");
 }

 static void save(Context context,String value)throws Exception {
  String trimmed=value==null?"":value.trim();
  if(!valid(trimmed))throw new IllegalArgumentException(invalidMessage(trimmed));
  Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,key());
  byte[] iv=cipher.getIV(),encrypted=cipher.doFinal(trimmed.getBytes(StandardCharsets.UTF_8)),combined=new byte[iv.length+encrypted.length];
  System.arraycopy(iv,0,combined,0,iv.length);System.arraycopy(encrypted,0,combined,iv.length,encrypted.length);
  context.getSharedPreferences(PREF,0).edit().putString(KEY,Base64.encodeToString(combined,Base64.NO_WRAP)).apply();
 }

 static String load(Context context){
  String encoded=context.getSharedPreferences(PREF,0).getString(KEY,null);
  if(encoded==null)return "";
  try{
   byte[] bytes=Base64.decode(encoded,Base64.NO_WRAP);
   if(bytes.length<30||bytes.length>24576)return "";
   Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.DECRYPT_MODE,key(),new GCMParameterSpec(128,bytes,0,12));
   String value=new String(cipher.doFinal(bytes,12,bytes.length-12),StandardCharsets.UTF_8);
   return valid(value)?value:"";
  }catch(Exception invalid){return "";}
 }

 static boolean saved(Context context){return !load(context).isEmpty();}

 static void clear(Context context){context.getSharedPreferences(PREF,0).edit().remove(KEY).apply();}

 static String invalidMessage(String value){
  if(value!=null&&value.startsWith("tskey-api-"))return "这是 Tailscale API 密钥，不能用于设备登录；请生成以 tskey-auth- 开头的 Auth Key。";
  return "请输入以 tskey-auth- 开头的 Tailscale Auth Key。";
 }
}
