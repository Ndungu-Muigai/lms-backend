import random
import string

def get_otp():
    # Select 2 random uppercase letters
    letters = [random.choice(string.ascii_uppercase) for _ in range(2)]
    
    # Select 4 random digits between 0 and 9
    numbers = [random.choice(string.digits) for _ in range(4)]
    
    # Combine the letters and numbers
    code = letters + numbers
    
    # Shuffle the combined list to randomize the order
    random.shuffle(code)
    
    # Convert the list to a string
    code_string = ''.join(code)
    
    return code_string
