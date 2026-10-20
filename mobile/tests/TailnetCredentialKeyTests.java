package io.github.try2love.codexbridge;

public final class TailnetCredentialKeyTests {
 public static void main(String[] args){
  check(TailnetCredentialStore.valid("tskey-auth-abcdefghijklmnop"),"Auth Key must be accepted");
  for(String value:new String[]{
   "",
   "tskey-auth-",
   "tskey-api-abcdefghijklmnop",
   "tskey-client-abcdefghijklmnop",
   "tskey-auth-abcdefghijklmnop\n"
  })check(!TailnetCredentialStore.valid(value),"Non-auth credential must be rejected: "+value);
  check(TailnetCredentialStore.invalidMessage("tskey-api-abcdefghijklmnop").contains("Auth Key"),"API key error must explain the required key type");
  System.out.println("Tailscale credential checks passed");
 }

 static void check(boolean value,String message){
  if(!value)throw new AssertionError(message);
 }
}
