# Agent Note: Local Claude Code CLI attachments

Status: implemented

## Problem

The Claude Code CLI conversation had no attachment capability, although the shared composer and private upload ledger already supported image uploads for Claude Desktop. File uploads could not be sent with a CLI message.

## Decision

Keep the existing authenticated, conversation-scoped upload ledger. The HTTP send route resolves upload IDs after reading the selected session. Only a Claude CLI session explicitly identified as local may receive a nonimage file path; Desktop, DeepSeek and future remote CLI sessions retain their existing image-only boundary until a remote transport is implemented. Clients cannot submit resolved bytes or local paths directly.

The owned local CLI receives images as native stream-json image content blocks. At explicit resume, `--add-dir` grants its native Read tool access only to this conversation's private upload directory. The selected session keeps its existing cwd and profile. For nonimage files, the message includes the ledger-verified absolute path and asks Claude to read it. Textless attachment messages are valid. The UUID receipt ledger still prevents replay after an unknown write outcome. Saved histories continue through the existing transcript reader, which renders native image blocks as image markers and file references as text.

## Verification and limits

Claude Code 2.1.287 against an isolated loopback mock received the exact valid PNG bytes in its model request. Its Read tool denied an upload path outside the cwd without `--add-dir`, then returned the uploaded test file's bytes with the scoped directory added. No user profile, chats or paid model endpoint were used. Python contract and HTTP upload tests, plus shared attachment UI tests, passed. The native check verifies local macOS behavior; SSH file transport and other operating systems remain separate work.
