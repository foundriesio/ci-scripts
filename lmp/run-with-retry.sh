#!/bin/bash

num_attempts=3

# Check if at least one argument is provided, the first argument is treated
# as the command to execute.
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <command> [args...]"
  exit 1
fi

command=$1
shift  # Shift out the command

# Track the attempt count
attempt=1

# Try to execute the command with retries
while [[ $attempt -le $num_attempts ]]; do
  echo "Attempt $attempt/$num_attempts: Running '$command $@'"
  $command "$@"

  # Check if the command succeeded
  if [[ $? -eq 0 ]]; then
    echo "Command succeeded on attempt #$attempt"
    exit 0
  fi

  echo "Command failed on attempt #$attempt. Retrying..."
  attempt=$((attempt + 1))
done

echo "Command failed after $num_attempts attempts."
exit 1
