#!/usr/local/bin/python3
# coding: utf-8

# SearchGram - es.py
# 4/4/22 22:08
#

__author__ = "Benny <benny.think@gmail.com>"

import logging

import meilisearch

from .config import MEILI_HOST, MEILI_PASS
from .engine import BasicSearchEngine
from .utils import sizeof_fmt


class SearchEngine(BasicSearchEngine):
    def __init__(self):
        # ["BOT", "CHANNEL", "GROUP", "PRIVATE", "SUPERGROUP"]
        try:
            self.client = meilisearch.Client(MEILI_HOST, MEILI_PASS)

            # Try to create index, ignore if it already exists
            try:
                self.client.create_index("telegram", {"primaryKey": "ID"})
                logging.info("Created new MeiliSearch index: telegram")
            except meilisearch.errors.MeilisearchApiError as e:
                if "already exists" in str(e).lower():
                    logging.info("MeiliSearch index 'telegram' already exists, using existing index")
                else:
                    raise

            # Update index settings (these are idempotent, safe to run every time)
            self.client.index("telegram").update_filterable_attributes(["chat.id", "chat.username", "chat.type", "indexed_by_account"])
            self.client.index("telegram").update_ranking_rules(
                ["timestamp:desc", "words", "typo", "proximity", "attribute", "sort", "exactness"]
            )
            self.client.index("telegram").update_sortable_attributes(["timestamp"])
            # Enable faceting for chat.id to get list of synced chats per account
            self.client.index("telegram").update_faceting({"maxValuesPerFacet": 1000})
            logging.info("MeiliSearch initialized successfully")
        except Exception as e:
            logging.critical(f"Failed to connect to MeiliSearch: {e}")

    def upsert(self, message, account_id=None):
        if self.check_ignore(message):
            return
        data = self.set_uid(message, account_id)
        self.client.index("telegram").add_documents([data], primary_key="ID")

    def search(self, keyword, _type=None, user=None, page=1, mode=None, account_id=None) -> dict:
        if mode:
            keyword = f'"{keyword}"'
        user = self.clean_user(user)
        params = {
            "hitsPerPage": 10,
            "page": page,
            "sort": ["timestamp:desc"],
            "matchingStrategy": "all",
            "filter": [],
        }
        if user:
            params["filter"].extend([f"chat.username = {user} OR chat.id = {user}"])
        if _type:
            params["filter"].extend([f"chat.type = ChatType.{_type}"])
        if account_id:
            params["filter"].extend([f"indexed_by_account = {account_id}"])
        logging.info("Search params: %s", params)
        return self.client.index("telegram").search(keyword, params)

    def ping(self):
        text = "Pong!\n"
        stats = self.client.get_all_stats()
        size = stats["databaseSize"]
        last_update = stats["lastUpdate"]
        for uid, index in stats["indexes"].items():
            text += f"Index {uid} has {index['numberOfDocuments']} documents\n"
        text += f"\nDatabase size: {sizeof_fmt(size)}\nLast update: {last_update}\n"
        return text

    def clear_db(self):
        self.client.index("telegram").delete()

    def delete_user(self, user):
        params = {
            "filter": [f"chat.username = {user} OR chat.id = {user}"],
            "hitsPerPage": 1000,
        }

        data = self.client.index("telegram").search("", params)
        for hit in data["hits"]:
            self.client.delete_index(hit["ID"])

    def delete_chat_for_account(self, account_id, chat_id):
        """Delete all messages for a specific chat indexed by a specific account."""
        try:
            # Use delete_documents with filter
            filter_str = f"indexed_by_account = {account_id} AND chat.id = {chat_id}"
            self.client.index("telegram").delete_documents(filter=filter_str)
            logging.info(f"Deleted messages from chat {chat_id} for account {account_id}")
        except Exception as e:
            logging.error(f"Failed to delete messages for chat {chat_id}, account {account_id}: {e}")

    def get_synced_chats_for_account(self, account_id):
        """Get list of chat IDs that have been synced for a specific account."""
        try:
            params = {
                "filter": [f"indexed_by_account = {account_id}"],
                "facets": ["chat.id"],
                "hitsPerPage": 0,  # We only want facets, not actual hits
            }
            result = self.client.index("telegram").search("", params)
            # Extract unique chat IDs from facet distribution
            if "facetDistribution" in result and "chat.id" in result["facetDistribution"]:
                return list(result["facetDistribution"]["chat.id"].keys())
            return []
        except Exception as e:
            logging.error(f"Failed to get synced chats for account {account_id}: {e}")
            return []


if __name__ == "__main__":
    search = SearchEngine()
    print(search.delete_user("InfSGK_bot"))
