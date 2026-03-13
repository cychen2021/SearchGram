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
from pyrogram import Client, filters, types

from . import SearchEngine
from .config import BOT_ID, get_sync_list
from .init_client import get_client
from .utils import setup_logger

setup_logger()

app = get_client()
tgdb = SearchEngine()
r = fakeredis.FakeStrictRedis()


@app.on_message((filters.outgoing | filters.incoming) & ~filters.chat(BOT_ID))
def message_handler(client: "Client", message: "types.Message"):
    logging.info("Adding new message: %s-%s", message.chat.id, message.id)
    tgdb.upsert(message)


@app.on_edited_message(~filters.chat(BOT_ID))
def message_edit_handler(client: "Client", message: "types.Message"):
    logging.info("Editing old message: %s-%s", message.chat.id, message.id)
    tgdb.upsert(message)


def safe_edit(msg, new_text):
    key = "sync-chat"
    if not r.exists(key):
        time.sleep(random.random())
        r.set(key, "ok", ex=2)
        msg.edit_text(new_text)


def sync_history():
    time.sleep(30)

    # Get sync list from config
    sync_items = get_sync_list()

    if not sync_items:
        logging.info("No chats configured for sync in config.toml")
        return

    saved = app.send_message("me", "Starting to sync history...")

    for uid in sync_items:
        try:
            # Try to get chat info first to populate Pyrogram's cache
            # This works better than resolve_peer for unknown peers
            chat = app.get_chat(uid)
            logging.info(f"Resolved peer for {uid}: {chat.first_name or chat.title}")
        except Exception as e:
            log = f"Failed to resolve peer {uid}: {e}. Make sure you have interacted with this user/chat before, or use their @username instead. Skipping..."
            logging.error(log)
            safe_edit(saved, log)
            time.sleep(2)
            continue

        try:
            total_count = app.get_chat_history_count(uid)
            log = f"Syncing history for {uid}"
            logging.info(log)
            safe_edit(saved, log)
            time.sleep(random.random())  # avoid flood
            chat_records = app.get_chat_history(uid)
            current = 0
            for msg in chat_records:
                safe_edit(saved, f"[{current}/{total_count}] - {log}")
                current += 1
                tgdb.upsert(msg)
        except Exception as e:
            log = f"Error syncing {uid}: {e}"
            logging.error(log)
            safe_edit(saved, log)
            time.sleep(2)
            continue

    log = "Sync history complete"
    logging.info(log)
    safe_edit(saved, log)


def main():
    threading.Thread(target=sync_history).start()
    app.run()


if __name__ == "__main__":
    main()
