# Source environment variables from .env file if it exists
if [ -f .env ]; then
    source .env
fi

# Start cursor editor
cursor .
