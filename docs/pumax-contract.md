# Pumax API Contract — Known Limitations

> **Status:** This document captures everything known about the MAX/Pumax API before writing code. It must be updated when new information becomes available.

## Library

`love-apples/maxapi` — Python library for MAX bot development.

Installation: `pip install maxapi`

Documentation: `https://github.com/love-apples/maxapi`

## Known Unknowns (Must Verify Before Code)

The following are **unknown and must be verified** before MLB-003 and MLB-005:

1. **Auth mechanism:**
   - Does maxapi handle session cookies automatically?
   - What does the login/session flow look like (URL, POST body, redirect)?
   - How is session state persisted — token, cookie jar, or something else?
   - Does maxapi expose a session object that can be stored/restored?

2. **Chat listing:**
   - Is there a method to list all personal (1:1) chats for the authenticated user?
   - What does the chat object look like (id, title, type, participants)?

3. **Message polling:**
   - Does maxapi have a built-in polling mechanism or do we need to poll `getMessages` manually?
   - What is the method signature for fetching new messages?
   - Does it return a cursor or offset for pagination?

4. **Message sending:**
   - Is there a `sendMessage(chatId, text)` equivalent?
   - Does it support media attachments (photo, video, audio)?

5. **Session expiry:**
   - How does maxapi signal an expired session — exception type, return value?
   - Can we detect expiry before making a request or only after a 401?

6. **Chat creation:**
   - Can we create a new MAX personal chat via API?
   - Or are chats only created by users from the MAX side?

## Verified: Confirmed by code inspection

_Nothing confirmed yet — will be updated as integration proceeds._

## Action Items Before Code

- [ ] Inspect `maxapi` source code on GitHub for session/auth implementation
- [ ] Find the exact method names for listing chats and fetching messages
- [ ] Test session persistence behavior locally
- [ ] Identify all exception types and their meaning
- [ ] Document supported message types (text, photo, video, audio, sticker, etc.)

## How to Update This Document

When a new fact about Pumax is discovered:
1. Move item from "Known Unknowns" to "Verified"
2. Record the exact method signature or API contract
3. Add any new unknown that appears
