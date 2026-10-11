"""Mailbox connectors. Each provider exposes the same four methods:

    account() -> str                       mailbox address
    list_before(cutoff) -> iter[str]       ids of messages received before cutoff
                                           (Trash and Spam/Junk are skipped)
    fetch_raw(id) -> (bytes, datetime)     full original message (.eml) + received time
    trash(id)                              move to Trash / Deleted Items (recoverable)
"""
