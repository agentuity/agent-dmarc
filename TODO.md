# DMARC Agent TODO

## 1. Email Integration (Gmail)
- [x] Implement Gmail API authentication and email fetching (see `gmail.py`)
- [x] Download and save email attachments

## 2. DMARC Report Parsing
- [x] Import parsedmarc library to parse XML and convert to JSON
- [x] LLM analyzing the parsed DMARC and generate summary

## 3. Slack Integration
- [x] Set up Slack API integration for sending messages
- [x] Send DMARC status summaries and alerts to a designated Slack channel

## 4. Support Slack Queries
- [ ] Allow Slack to ping the agent and answer questions accordingly
- [ ] Multi-action agent -- depending the user queries

---