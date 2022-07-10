import argparse
import random
import sys
sys.path.append('../../utils/gmail/')
from send_message import send_email

parser = argparse.ArgumentParser()
parser.add_argument("--to", default="oliffur@gmail.com", help="recipient")
args = parser.parse_args()

def main():
    with open('choices.txt', 'r') as f:
        cards = f.read().splitlines()

    # Shuffle if we've looped
    if cards[0] == "Bad|Good" or cards[1] == "Bad|Good":
        rest = cards[2:]
        random.shuffle(rest)
        cards = [cards[0], cards[1]] + rest

    # Deal the two cards
    message = '\n'.join([cards[0], cards[1]])
    send_email(toaddr=args.to, subject="WAVELENGTH", message=message)

    # Rotate array, write back out
    cards = cards[2:] + cards[:2]
    with open('choices.txt', 'w') as f:
        f.writelines(s + '\n' for s in cards)

if __name__ == "__main__":
    main()
