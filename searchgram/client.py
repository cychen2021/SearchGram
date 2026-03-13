#!/usr/local/bin/python3
# coding: utf-8

# SearchGram - client.py
# 4/4/22 22:06
#

__author__ = "Benny <benny.think@gmail.com>"

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
    logging.info("Adding new message: %s-%s", message.chat.id, message.id)
    # Get the account ID from the client's user (me)
    account_id = client.me.id
    tgdb.upsert(message, account_id=account_id)


def message_edit_handler(client: "Client", message: "types.Message"):
    if not _handlers_active:
        return  # Skip processing until all clients are ready
    logging.info("Editing old message: %s-%s", message.chat.id, message.id)
    # Get the account ID from the client's user (me)
    account_id = client.me.id
    tgdb.upsert(message, account_id=account_id)


async def sync_history(client):
    """Sync history for a specific client instance."""
    import asyncio
    await asyncio.sleep(30)

    # Get sync list from config
    sync_items = get_sync_list()

    if not sync_items:
        logging.info(f"[{client.name}] No chats configured for sync in config.toml")
        return

    saved = await client.send_message("me", f"[{client.name}] Starting to sync history...")

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
            chat_records = client.get_chat_history(uid)
            current = 0
            account_id = client.me.id
            async for msg in chat_records:
                if current % 10 == 0:  # Update progress every 10 messages
                    try:
                        await saved.edit_text(f"[{client.name}] [{current}/{total_count}] - {log}")
                    except:
                        pass
                current += 1
                tgdb.upsert(msg, account_id=account_id)
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


def main():
    from pyrogram import idle
    import asyncio

    async def run():
        # Step 1: Register message handlers on all clients BEFORE starting
        for client in clients:
            client.on_message((filters.outgoing | filters.incoming) & ~filters.chat(BOT_ID))(message_handler)
            client.on_edited_message(~filters.chat(BOT_ID))(message_edit_handler)

        # Step 2: Authenticate and start all clients sequentially
        logging.info(f"Authenticating {len(clients)} session(s)...")

        # Temporarily suppress Pyrogram's verbose internal logging during authentication
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

        # Step 3: Activate message handlers now that all clients are ready
        global _handlers_active
        _handlers_active = True
        logging.info("Message processing activated for all clients!")

        # Step 4: Start sync history tasks for each client
        logging.info("Starting history sync tasks...")
        for client in clients:
            asyncio.create_task(sync_history(client))

        # Step 5: Keep all clients running
        logging.info("✓ All clients are now running. Press Ctrl+C to stop.")
        await idle()

        # Stop all clients on exit
        for client in clients:
            await client.stop()

    # Run the async function
    asyncio.run(run())


if __name__ == "__main__":
    main()
