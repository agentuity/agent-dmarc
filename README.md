<div align="center">
    <img src="https://raw.githubusercontent.com/agentuity/cli/refs/heads/main/.github/Agentuity.png" alt="Agentuity" width="100"/> <br/>
    <strong>Build Agents, Not Infrastructure</strong> <br/>
<br />
</div>

# 📧 DMARC Email Report Processing Agent

Welcome to the DMARC Email Processing Agent! This project automatically monitors Gmail for DMARC reports, processes them, and sends notifications to Slack. Built with the Agentuity platform for reliable, scalable email automation.

## 📋 Prerequisites

Before you begin, ensure you have the following installed:

- **Python**: Version 3.10 or higher
- **UV**: Version 0.5.25 or higher ([Documentation](https://docs.astral.sh/uv/))

## 🚀 Getting Started

### Authentication

Before using Agentuity, you need to authenticate:

```bash
agentuity login
```

This command will open a browser window where you can log in to your Agentuity account.

### Development Mode

Run your project in development mode with:

```bash
agentuity dev
```

This will start your project and open a new browser window connecting your Agent to the Agentuity Console in Live Mode, allowing you to test and debug your agent in real-time.

You can also start your project in development mode without connecting to the Agentuity Console:

```bash
uv run --env-file .env server.py
```

## 📚 Project Structure

```
├── agents/             # Agent definitions and implementations
│   └── dmarc_email/    # DMARC email processing agent
├── utils/              # Utility modules
│   ├── gmail.py        # Gmail API authentication and email processing
│   └── slack.py        # Slack integration utilities
├── resources/          # Resource files and templates
│   └── templates.py    # Email and notification templates
├── bin/                # Scripts and executables
│   └── develop.sh      # Development setup script
├── .agentuity/         # Agentuity configuration files
├── pyproject.toml      # Project dependencies and metadata
├── uv.lock             # UV lock file for reproducible builds
├── server.py           # Server entry point
├── main.py             # Main application entry point
└── agentuity.yaml      # Agentuity project configuration
```

## 🔄 Agent Flow Diagram

The DMARC Email Processing Agent follows a structured workflow starting from the `run()` method in `agents/dmarc_email/agent.py`:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│                           AGENT ENTRY POINT                             │
│                                                                         │
│  ┌─────────────┐                                                        │
│  │             │                                                        │
│  │  run()      │  Entry point that initiates the DMARC processing flow  │
│  │             │                                                        │
│  └──────┬──────┘                                                        │
│         │                                                               │
│         ▼                                                               │
│  ┌─────────────────────┐                                                │
│  │                     │                                                │
│  │ generate_dmarc_     │  Orchestrates the entire DMARC workflow        │
│  │ report()            │                                                │
│  │                     │                                                │
│  └─────────┬───────────┘                                                │
│            │                                                            │
└────────────┼────────────────────────────────────────────────────────────┘
             │
             │    ┌───────────────────────────────────────────────────────┐
             │    │                                                       │
             │    │                 EMAIL PROCESSING                      │
             │    │                                                       │
             ├───▶│  ┌────────────────────┐                              │
             │    │  │                    │                              │
             │    │  │ authenticate_      │  Authenticates with Gmail    │
             │    │  │ gmail()            │  using OAuth                 │
             │    │  │                    │                              │
             │    │  └──────────┬─────────┘                              │
             │    │             │                                         │
             │    │             ▼                                         │
             │    │  ┌────────────────────┐                              │
             │    │  │                    │                              │
             │    │  │ get_unread_dmarc_  │  Retrieves unread emails     │
             │    │  │ emails()           │  with attachments            │
             │    │  │                    │                              │
             │    │  └──────────┬─────────┘                              │
             │    │             │                                         │
             │    │             ▼                                         │
             │    │  ┌────────────────────┐                              │
             │    │  │                    │                              │
             │    │  │ get_dmarc_         │  Extracts DMARC XML reports  │
             │    │  │ attachment_        │  from email attachments      │
             │    │  │ content()          │  (.xml, .zip, .gz)           │
             │    │  │                    │                              │
             │    │  └────────────────────┘                              │
             │    │                                                       │
             │    └───────────────────────────────────────────────────────┘
             │
             │    ┌───────────────────────────────────────────────────────┐
             │    │                                                       │
             │    │                 ANALYSIS PROCESSING                   │
             │    │                                                       │
             ├───▶│  ┌────────────────────┐                              │
             │    │  │                    │                              │
             │    │  │ analyze_dmarc_and_ │  Processes each DMARC report │
             │    │  │ slack_result()     │  and sends results to Slack  │
             │    │  │                    │                              │
             │    │  └──────────┬─────────┘                              │
             │    │             │                                         │
             │    │             ▼                                         │
             │    │  ┌────────────────────┐                              │
             │    │  │                    │                              │
             │    │  │ analyze_dmarc_     │  Uses OpenAI GPT-4o to       │
             │    │  │ report()           │  analyze XML reports         │
             │    │  │                    │  with analyze-dmarc template │
             │    │  └──────────┬─────────┘                              │
             │    │             │                                         │
             │    │             ▼                                         │
             │    │  ┌────────────────────┐                              │
             │    │  │                    │                              │
             │    │  │ summarize_         │  Generates concise summary   │
             │    │  │ analysis()         │  with summarize-analysis     │
             │    │  │                    │  template                    │
             │    │  └──────────┬─────────┘                              │
             │    │             │                                         │
             │    │             ▼                                         │
             │    │  ┌────────────────────┐                              │
             │    │  │                    │                              │
             │    │  │ slack_to_dmarc_    │  Sends analysis to Slack     │
             │    │  │ channel()          │  channel                     │
             │    │  │                    │                              │
             │    │  └────────────────────┘                              │
             │    │                                                       │
             │    └───────────────────────────────────────────────────────┘
             │
             │    ┌───────────────────────────────────────────────────────┐
             │    │                                                       │
             │    │                 POST PROCESSING                       │
             │    │                                                       │
             └───▶│  ┌────────────────────┐                              │
                  │  │                    │                              │
                  │  │ post_process_      │  Stores results and marks    │
                  │  │ dmarc_emails()     │  emails as read              │
                  │  │                    │                              │
                  │  └────────────────────┘                              │
                  │                                                       │
                  └───────────────────────────────────────────────────────┘
```

### Input and Output

#### Input
- **DMARC Report Emails**: Unread emails in Gmail with DMARC report attachments
- **Attachment Types**: XML, ZIP, or GZ files containing DMARC reports
- **XML Content**: DMARC reports in XML format containing authentication results

#### Processing
1. **Authentication**: OAuth with Gmail API
2. **Email Retrieval**: Fetch unread emails with attachments
3. **Extraction**: Parse and extract DMARC XML reports from attachments
4. **Analysis**: Process reports using OpenAI GPT-4o with specialized prompts
5. **Summarization**: Generate concise summaries of analysis results

#### Output
- **JSON Response**: Summary of DMARC analysis returned by the agent
- **Slack Notifications**: Analysis results sent to configured Slack channel
- **Storage**: Results stored in key-value store for future reference

## 🔧 Configuration

Your project configuration is stored in `agentuity.yaml`. This file defines your agents, development settings, and deployment configuration.

## 🛠️ Advanced Usage

### Environment Variables

You can set environment variables for your project:

```bash
agentuity env set KEY=VALUE
```

### Secrets Management

For sensitive information, use secrets:

```bash
agentuity env set --secret KEY=VALUE
```

## 🚀 Production Deployment

To deploy this agent in a production environment (non-interactive, headless, or cloud):

### 1. Generate Gmail OAuth Token Locally
- Generate a `credentials.json` from the Google Cloud Console for the gmail account which your agent will use to read inboxes from
- Put `credentials.json` in the root directory
- Run the agent locally with `agentuity dev`, and send a simple POST request to your agent. This will trigger an OAuth browser flow which is require to generate authentication token (`token.json`) that will be used to authenticate your agent
- To get the valid value for `GOOGLE_AUTH_TOKEN` required for step #1, run: `base64 -w 0 token.json` and copy the output of this encoding into `.env` variable. The token is a complex json, and the gmail authenticator is expecting a base64 encoded JSON string.

### 2. Set Required Environment Variables
Set the following environment variables in your production environment `.env`

```
GOOGLE_AUTH_TOKEN=<base64 encoding of your token.json content>
SLACK_BOT_TOKEN=<your Slack bot token>
DMARC_CHANNEL_ID=<your Slack channel ID>
AGENTUITY_SDK_KEY=<your Agentuity SDK key>
ENVIRONMENT=production|development
```

### 3. Import Project
- If you don't already have a project created for this project, you can run `agentuity project import` in this repository to import this project to your Agentuity account. This will create a new Agentuity project, and automatically updates `agentuity.yaml` to point to your new project and agent_id

### 3. Deploy Your Code
- Ensure your environment variables are set
- Deploy your project to production with `agentuity deploy`

### 4. Run Your App
- Copy and paste the link generated by the previous `agentuity deploy` to your browser. If you cannot find it - visit your agentuity dashboard and find your DMARC project.
- Set up webhook or cron job for your `dmarc_email` agent -- you can find that in `Agents` tab of your DMARC project.

**Note:** You should NOT run the OAuth browser flow in production. Run it locally and set a valid `GOOGLE_AUTH_TOKEN` to `.env`.

## 📖 Documentation

For comprehensive documentation on the Agentuity Python SDK, visit:
[https://agentuity.dev/SDKs/python](https://agentuity.dev/SDKs/python)

## 🆘 Troubleshooting

If you encounter any issues:

1. Check the [documentation](https://agentuity.dev/SDKs/python)
2. Join our [Discord community](https://discord.com/invite/vtn3hgUfuc) for support
3. Contact the Agentuity support team

## 📝 License

This project is licensed under the terms specified in the LICENSE file.
