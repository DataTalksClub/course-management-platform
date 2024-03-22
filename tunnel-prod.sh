#!/bin/bash

echo "connecting to SSH and setting up the SSH tunnel..."
BASTION_NAME="bastion-tunnel"
ssh -f -N "${BASTION_NAME}"

# Get the PID of the SSH process for later termination
SSH_PID=$!

export DATABASE_URL="postgresql://pgusr:${DB_PASSWORD}@localhost:5433/prod"
export SECRET_KEY="${DJANGO_SECRET}"

echo "SSH tunnel established. Starting shell..."
/bin/bash

# When the shell is closed, kill the SSH tunnel
echo "Shell closed. Terminating SSH tunnel..."
kill $SSH_PID
