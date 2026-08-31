def email_campaign_to_dict(email_campaign):
    return {
        "id": email_campaign.id,
        "registration_campaign": email_campaign.registration_campaign.slug,
        "subject": email_campaign.subject,
        "preview_text": email_campaign.preview_text,
        "body_markdown": email_campaign.body_markdown,
        "status": email_campaign.status,
    }
