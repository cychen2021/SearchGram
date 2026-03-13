#!/usr/local/bin/python3
# coding: utf-8

# SearchGram - client.py
# 4/4/22 22:06
#

__author__ = "Benny <benny.think@gmail.com>"

import logging
import random
import threading
import time

import fakeredis
from pyrogram import Client, compose, filters, types

from . import SearchEngine
from .config import BOT_ID, get_sessions, get_sync_list
from .init_client import get_client
from .utils import setup_logger

setup_logger()

tgdb = SearchEngine()
r = fakeredis.FakeStrictRedis()

# Create multiple client instances based on configuration
sessions = get_sessions()
clients = [get_client(session_name=session) for session in sessions]
logging.info(f"Initialized {len(clients)} client(s) with sessions: {sessions}")


# Define handlers that will be registered on all clients after authentication
def message_handler(client: "Client", message: "types.Message"):
    logging.info("Adding new message: %s-%s", message.chat.id, message.id)
    # Get the account ID from the client's user (me)
    account_id = client.me.id
    tgdb.upsert(message, account_id=account_id)


def message_edit_handler(client: "Client", message: "types.Message"):
    logging.info("Editing old message: %s-%s", message.chat.id, message.id)
    # Get the account ID from the client's user (me)
    account_id = client.me.id
    tgdb.upsert(message, account_id=account_id)


def safe_edit(msg, new_text):
    key = "sync-chat"
    if not r.exists(key):
        time.sleep(random.random())
        r.set(key, "ok", ex=2)
        msg.edit_text(new_text)


def sync_history(client):
    """Sync history for a specific client instance."""
    time.sleep(30)

    # Get sync list from config
    sync_items = get_sync_list()

    if not sync_items:
        logging.info(f"[{client.name}] No chats configured for sync in config.toml")
        return

    saved = client.send_message("me", f"[{client.name}] Starting to sync history...")

    for uid in sync_items:
        try:
            # Try to get chat info first to populate Pyrogram's cache
            # This works better than resolve_peer for unknown peers
            chat = client.get_chat(uid)
            logging.info(f"[{client.name}] Resolved peer for {uid}: {chat.first_name or chat.title}")
        except Exception as e:
            log = f"[{client.name}] Failed to resolve peer {uid}: {e}. Make sure you have interacted with this user/chat before, or use their @username instead. Skipping..."
            logging.error(log)
            safe_edit(saved, log)
            time.sleep(2)
            continue

        try:
            total_count = client.get_chat_history_count(uid)
            log = f"[{client.name}] Syncing history for {uid}"
            logging.info(log)
            safe_edit(saved, log)
            time.sleep(random.random())  # avoid flood
            chat_records = client.get_chat_history(uid)
            current = 0
            account_id = client.me.id if hasattr(client, 'me') and client.me else None
            for msg in chat_records:
                safe_edit(saved, f"[{client.name}] [{current}/{total_count}] - {log}")
                current += 1
                tgdb.upsert(msg, account_id=account_id)
        except Exception as e:
            log = f"[{client.name}] Error syncing {uid}: {e}"
            logging.error(log)
            safe_edit(saved, log)
            time.sleep(2)
            continue

    log = f"[{client.name}] Sync history complete"
    logging.info(log)
    safe_edit(saved, log)


def main():
    from pyrogram import idle
    import asyncio

    async def run():
        # Step 1: Check and authenticate any unauthenticated clients sequentially
        logging.info(f"Checking authentication status for {len(clients)} session(s)...")

        for i, client in enumerate(clients, 1):
            await client.connect()
            is_authorized = await client.is_authorized()

            if not is_authorized:
                print(f"\n{'='*60}")
                print(f"  [{i}/{len(clients)}] Authenticating session: {client.name}")
                print(f"{'='*60}")
                # Disconnect and use start() for interactive authentication
                await client.disconnect()
                await client.start()
                # Stop immediately after authentication to prevent message processing
                await client.stop()
                logging.info(f"[{i}/{len(clients)}] ✓ Authenticated successfully")
            else:
                me = await client.get_me()
                logging.info(f"[{i}/{len(clients)}] ✓ Already authenticated as: {me.first_name} (ID: {me.id})")
                await client.disconnect()

        logging.info("All sessions authenticated successfully!")

        # Step 2: Register message handlers on all clients
        logging.info("Registering message handlers...")
        for client in clients:
            client.on_message((filters.outgoing | filters.incoming) & ~filters.chat(BOT_ID))(message_handler)
            client.on_edited_message(~filters.chat(BOT_ID))(message_edit_handler)
        logging.info("Message handlers registered!")

        # Step 3: Start ALL clients together
        logging.info("Starting all clients together...")
        for i, client in enumerate(clients, 1):
            await client.start()
            me = await client.get_me()
            logging.info(f"[{i}/{len(clients)}] Started: {me.first_name} (ID: {me.id})")

        # Step 4: Start sync history threads for each client
        logging.info("Starting history sync threads...")
        for client in clients:
            threading.Thread(target=sync_history, args=(client,), daemon=True).start()

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
