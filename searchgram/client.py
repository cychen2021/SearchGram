#!/usr/local/bin/python3
# coding: utf-8

# SearchGram - client.py
# 4/4/22 22:06
#

__author__ = "Benny <benny.think@gmail.com>"

import builtins
import getpass
import logging
import random

from pyrogram import Client, compose, filters, types

from . import SearchEngine
from .config import BOT_ID, get_sessions, get_sync_list
from .init_client import get_client
from .utils import setup_logger

setup_logger()

tgdb = SearchEngine()

# Create multiple client instances based on configuration
sessions = get_sessions()
clients = [get_client(session_name=session) for session in sessions]
logging.info(f"Initialized {len(clients)} client(s) with sessions: {sessions}")

# Flag to control when message processing should begin
_handlers_active = False


# Define handlers that will be registered on all clients after authentication
def message_handler(client: "Client", message: "types.Message"):
    if not _handlers_active:
        return  # Skip processing until all clients are ready

    logging.info(f"[{client.name}] Adding new message: {message.chat.id}-{message.id} (type: {message.chat.type.name})")

    # Get the account ID from the client's user (me)
    account_id = client.me.id

    # Check if message will be ignored
    if tgdb.check_ignore(message):
        logging.warning(f"[{client.name}] Message {message.chat.id}-{message.id} ignored by whitelist/blacklist (chat_type: {message.chat.type.name})")
        return

    tgdb.upsert(message, account_id=account_id)


def message_edit_handler(client: "Client", message: "types.Message"):
    if not _handlers_active:
        return  # Skip processing until all clients are ready

    logging.info(f"[{client.name}] Editing old message: {message.chat.id}-{message.id} (type: {message.chat.type.name})")

    # Get the account ID from the client's user (me)
    account_id = client.me.id

    if tgdb.check_ignore(message):
        logging.warning(f"[{client.name}] Edited message {message.chat.id}-{message.id} ignored by whitelist/blacklist (chat_type: {message.chat.type.name})")
        return

    tgdb.upsert(message, account_id=account_id)


async def sync_history(client):
    """Sync history for a specific client instance."""
    import asyncio
    await asyncio.sleep(30)

    # Get sync list for this specific session
    sync_items = get_sync_list(session_name=client.name)

    if not sync_items:
        logging.info(f"[{client.name}] No chats configured for sync in config.toml")
        return

    saved = await client.send_message("me", f"[{client.name}] Starting to sync history...")

    # Cleanup: delete messages from chats that are no longer in the sync list
    account_id = client.me.id
    try:
        synced_chats = tgdb.get_synced_chats_for_account(account_id)
        # Resolve sync_items to chat IDs for comparison
        sync_chat_ids = set()
        for uid in sync_items:
            try:
                # Try to resolve each item to get its numeric chat ID
                chat = await client.get_chat(uid)
                sync_chat_ids.add(str(chat.id))
            except:
                # If resolution fails, keep the original value for comparison
                sync_chat_ids.add(str(uid).lstrip('@'))

        for chat_id in synced_chats:
            # Check if this chat is still in the sync list
            if chat_id not in sync_chat_ids:
                logging.info(f"[{client.name}] Removing messages from chat {chat_id} (no longer in sync list)")
                tgdb.delete_chat_for_account(account_id, chat_id)
    except Exception as e:
        logging.error(f"[{client.name}] Error during cleanup: {e}")

    for uid in sync_items:
        try:
            # Try to get chat info first to populate Pyrogram's cache
            # This works better than resolve_peer for unknown peers
            chat = await client.get_chat(uid)
            logging.info(f"[{client.name}] Resolved peer for {uid}: {chat.first_name or chat.title}")
        except Exception as e:
            log = f"[{client.name}] Failed to resolve peer {uid}: {e}. Make sure you have interacted with this user/chat before, or use their @username instead. Skipping..."
            logging.error(log)
            try:
                await saved.edit_text(log)
            except:
                pass
            await asyncio.sleep(2)
            continue

        try:
            total_count = await client.get_chat_history_count(uid)
            log = f"[{client.name}] Syncing history for {uid}"
            logging.info(log)
            try:
                await saved.edit_text(log)
            except:
                pass
            await asyncio.sleep(random.random())  # avoid flood

            # Use try/finally to ensure the async iterator is properly closed
            chat_records = client.get_chat_history(uid)
            current = 0
            skipped = 0
            inserted = 0
            account_id = client.me.id

            try:
                async for msg in chat_records:
                    if current % 10 == 0:  # Update progress every 10 messages
                        try:
                            await saved.edit_text(f"[{client.name}] [{current}/{total_count}] ({inserted} new, {skipped} skipped) - {log}")
                        except:
                            pass
                    current += 1

                    # Skip if message already exists
                    if tgdb.message_exists(msg.chat.id, msg.id):
                        skipped += 1
                        # Yield to event loop periodically to allow new messages to be processed
                        if skipped % 50 == 0:
                            await asyncio.sleep(0)
                        continue

                    tgdb.upsert(msg, account_id=account_id)
                    inserted += 1

                    # Yield to event loop every few messages to allow incoming messages to be processed
                    if inserted % 5 == 0:
                        await asyncio.sleep(0)
            finally:
                # Ensure the async iterator is properly closed to avoid leaving client in bad state
                await chat_records.aclose()

            # Log completion stats
            completion_log = f"[{client.name}] Completed {uid}: {inserted} new messages, {skipped} skipped"
            logging.info(completion_log)
            try:
                await saved.edit_text(completion_log)
            except:
                pass

            # Yield to event loop after completing each chat to ensure pending updates are processed
            await asyncio.sleep(0.1)

        except Exception as e:
            log = f"[{client.name}] Error syncing {uid}: {e}"
            logging.error(log)
            try:
                await saved.edit_text(log)
            except:
                pass
            await asyncio.sleep(2)
            continue

    log = f"[{client.name}] Sync history complete"
    logging.info(log)
    try:
        await saved.edit_text(log)
    except:
        pass

    # Final yield to ensure event loop processes any pending updates after sync completes
    logging.info(f"[{client.name}] Yielding control to process pending updates...")
    await asyncio.sleep(0.5)


def main():
    from pyrogram import idle
    import asyncio

    # Monkey-patch input to use getpass for password prompts
    _original_input = builtins.input

    def _secure_input(prompt=""):
        # If prompt contains "password", use getpass to hide input
        if "password" in prompt.lower():
            return getpass.getpass(prompt)
        return _original_input(prompt)

    builtins.input = _secure_input

    async def run():
        # Step 1: Authenticate and start all clients sequentially
        logging.info(f"Authenticating {len(clients)} session(s)...")

        # Step 2: Temporarily suppress Pyrogram's verbose internal logging during authentication
        pyrogram_logger = logging.getLogger("pyrogram")
        original_level = pyrogram_logger.level
        pyrogram_logger.setLevel(logging.WARNING)

        for i, client in enumerate(clients, 1):
            print(f"\n{'='*60}")
            print(f"  [{i}/{len(clients)}] Session: {client.name}")
            print(f"{'='*60}")
            # start() handles both new auth (with prompts) and existing sessions
            await client.start()
            me = await client.get_me()
            logging.info(f"[{i}/{len(clients)}] ✓ Authenticated as: {me.first_name} (ID: {me.id})")

        # Restore original logging level
        pyrogram_logger.setLevel(original_level)

        logging.info("All sessions authenticated successfully!")
        print()  # Add blank line for cleaner output

        # Step 3: Register message handlers on all clients AFTER authentication
        logging.info(f"Registering message handlers on {len(clients)} client(s) (excluding BOT_ID: {BOT_ID})...")
        for client in clients:
            client.on_message((filters.outgoing | filters.incoming) & ~filters.chat(BOT_ID))(message_handler)
            client.on_edited_message(~filters.chat(BOT_ID))(message_edit_handler)
        logging.info("Handlers registered successfully!")

        # Step 4: Activate message handlers now that all clients are ready
        global _handlers_active
        _handlers_active = True
        logging.info("Message processing activated for all clients!")

        # Step 5: Start sync history tasks for each client
        logging.info("Starting history sync tasks...")
        for client in clients:
            asyncio.create_task(sync_history(client))

        # Step 6: Keep all clients running
        logging.info("✓ All clients are now running. Press Ctrl+C to stop.")
        await idle()

        # Stop all clients on exit
        for client in clients:
            await client.stop()

    try:
        # Run the async function
        asyncio.run(run())
    finally:
        # Restore original input function
        builtins.input = _original_input


if __name__ == "__main__":
    main()
