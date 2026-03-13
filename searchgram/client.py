#!/usr/local/bin/python3
# coding: utf-8

# SearchGram - client.py
# 4/4/22 22:06
#

__author__ = "Benny <benny.think@gmail.com>"

import configparser
import logging
import random
import threading
import time

import fakeredis
from pyrogram import Client, filters, types

from . import SearchEngine
from .config import BOT_ID
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
    config = configparser.ConfigParser(allow_no_value=True)
    config.optionxform = lambda option: option

    # Read config file, handle if it doesn't exist
    files_read = config.read("sync.ini")
    if not files_read:
        logging.warning("sync.ini not found, skipping history sync")
        return

    # Ensure required sections exist
    if not config.has_section("sync"):
        logging.warning("No [sync] section in sync.ini, skipping history sync")
        return

    if not config.has_section("blacklist"):
        config.add_section("blacklist")

    if not config.has_section("whitelist"):
        config.add_section("whitelist")

    # Check if there are any items to sync
    sync_items = config.options("sync")
    if sync_items:
        saved = app.send_message("me", "Starting to sync history...")

        for uid in sync_items:
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
            config.remove_option("sync", uid)

        with open("sync.ini", "w") as configfile:
            config.write(configfile)

        log = "Sync history complete"
        logging.info(log)
        safe_edit(saved, log)
    else:
        logging.info("No chats configured for sync")


def main():
    threading.Thread(target=sync_history).start()
    app.run()


if __name__ == "__main__":
    main()
