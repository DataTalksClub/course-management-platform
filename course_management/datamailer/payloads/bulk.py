def bulk_recipient_list_payload(config, list_data, members):
    return {
        "audience": config.audience,
        "client": config.client,
        "list": list_data,
        "members": members,
    }
