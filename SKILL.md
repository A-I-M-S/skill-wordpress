---
name: skill-wordpress  
description: "Automated SEO autoblogging and multi-platform distribution system. Use when generating long-form SEO content, publishing to WordPress, distributing content across platforms like LinkedIn, Threads, Facebook, Telegram, Discord, Bluesky, Hashnode, WordPress.com, and Nostr, and triggering IndexNow indexing."
---

# OpenClaw SEO Autoblogging

Automate SEO content generation, publishing, and distribution across multiple platforms.

## Overview

This skill runs a full SEO autoblogging pipeline:
- AI-generated long-form articles  
- WordPress publishing  
- Multi-platform distribution  
- Indexing via IndexNow  

## Agent Guidance

Treat this skill as a content automation engine.

When invoked, the expected flow is:
- generate SEO article  
- publish to WordPress  
- distribute content  
- trigger indexing  

## Installation

git clone <repo-url>  
cd <repo>  
pip install -r requirements.txt  
cp .env.sample .env  

## Initialisation

Before running the main pipeline, fetch WordPress categories:

python3 wordpress-fetch-categories.py  

This generates:
- wordpress-categories.json  

This file is required for category selection during content publishing.

## Running

python3 wordpress-automation.py 1  

Modes:
- 1 → OpenRouter  
- 2 → NVIDIA  
- 3 → Gemini  

## Distribution Channels

### In Place
- LinkedIn (personal)  
- Threads  
- Facebook page  
- Telegram  
- Discord  
- Bluesky  
- Hashnode  
- WordPress.com  
- Nostr  

## Indexing

- IndexNow integration  

## Notes

- Designed for automation and scale  
- External APIs may change behavior  
- Ensure wordpress-categories.json exists before running  
- Refresh categories periodically if WordPress categories change