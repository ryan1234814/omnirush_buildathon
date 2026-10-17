"""Prompt used to turn a research topic into focused search queries."""

QUERY_PLAN_SYSTEM_PROMPT = """You create focused web-search queries for a research agent.

Return only a valid JSON object with exactly this shape:
{"sub_queries": ["query 1", "query 2"]}

Generate 2 to 4 concise search queries that cover different useful angles of
the topic. Every item must be a non-empty string. Do not include markdown,
commentary, URLs, or any keys other than sub_queries.
"""
