import secrets
import random
import string

def random_password():
    # Define character sets
    uppercase = string.ascii_uppercase
    lowercase = string.ascii_lowercase
    digits = string.digits
    special_characters = string.punctuation

    # Ensure the password contains at least one of each required character type
    password = [
        secrets.choice(uppercase),
        secrets.choice(lowercase),
        secrets.choice(digits),
        secrets.choice(special_characters)
    ]

    # Fill the rest of the password with random characters
    all_characters = uppercase + lowercase + digits + special_characters
    password += [secrets.choice(all_characters) for _ in range(6)]

    # Shuffle the result to avoid predictable patterns
    random.shuffle(password)

    return ''.join(password)