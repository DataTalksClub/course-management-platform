"""
Mailchimp integration for newsletter subscriptions
"""
import os
import logging
import hashlib
import requests

logger = logging.getLogger(__name__)

MAILCHIMP_TOKEN = os.getenv("MAILCHIMP_TOKEN", "")
MAILCHIMP_LIST_ID = os.getenv("MAILCHIMP_LIST_ID", "")


def add_subscriber_to_mailchimp(email: str, tag: str = None) -> bool:
    """
    Add or update a subscriber in Mailchimp
    
    Args:
        email: The email address to subscribe
        tag: Optional tag to add to the subscriber
        
    Returns:
        True if successful, False otherwise
    """
    if not MAILCHIMP_TOKEN or not MAILCHIMP_LIST_ID:
        logger.warning("Mailchimp not configured - skipping subscription")
        return False
    
    try:
        # Create MD5 hash of lowercase email for subscriber_hash
        subscriber_hash = hashlib.md5(email.lower().encode()).hexdigest()
        
        # Prepare the data
        data = {
            "email_address": email,
            "status_if_new": "subscribed",
        }
        
        # Add tags if provided
        if tag:
            data["tags"] = [tag]
        
        # Mailchimp API URL
        mc_url = f"https://us19.api.mailchimp.com/3.0/lists/{MAILCHIMP_LIST_ID}/members/{subscriber_hash}"
        
        # Make the request
        response = requests.put(
            mc_url,
            auth=("anystring", MAILCHIMP_TOKEN),
            headers={"Content-Type": "application/json"},
            json=data,
            timeout=10,
        )
        
        if response.status_code in [200, 201]:
            logger.info(f"Successfully added {email} to Mailchimp with tag {tag}")
            return True
        else:
            logger.error(f"Mailchimp API error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error adding subscriber to Mailchimp: {e}")
        return False
