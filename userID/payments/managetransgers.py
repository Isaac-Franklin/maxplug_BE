import uuid

# generate_idempotency_key
def generate_transaction_key():
    return str(uuid.uuid4())