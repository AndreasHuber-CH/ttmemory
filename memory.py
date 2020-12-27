#!/usr/bin/env python3

import sys
import argparse
import yaml
import os.path
import subprocess
from PIL import Image, ImageDraw, ImageFont
import math
import re

def fatalError(message):
    print(f'ERROR: {message}')
    sys.exit(1)

# path to tttool executable
tttool = os.path.expanduser("~/bin/tttool")

parser = argparse.ArgumentParser(description='Generate a memory game for TipToi')
parser.add_argument('template', help='Input yaml template file. Please specify a "memory" section to configure the generation. All other fields are copied over into the generated file.')
parser.add_argument('-y', '--yml-only', action='store_true', help='generate yaml file only')
parser.add_argument('-p', '--play', action='store_true', help='generate yaml file optimized for tttool play modus and start the play modus')

args = parser.parse_args()

with open(args.template) as f:
    game = yaml.load(f, Loader=yaml.FullLoader)

if not type(game) is dict:
    print('ERROR: Invalid input file.')
    sys.exit(1)
if not 'memory' in game:
    print('WARNING: "memory" section not found in yaml file. Using default values for all settings.')
    game['memory'] = {}
if not 'product-id' in game:
    fatalError('no "product-id" found in the input yaml file.')

# Read configuration values from the 'memory' entry in the yaml file:
# Max number of players
players = game['memory'].get('maxPlayers', 4)
# List of the pairs, there will be twice as many cards
pairs = game['memory']['pairs']
# If set to True, two different sound P(m_a) and P(m_b) are used for matching pairs instead of using the same sound P(m) for both cards.
alternativeSounds = game['memory'].get('alternativeSounds', False)
# Image dimensions in mm
imgWidth = game['memory'].get('imgWidth', 190)
imgHeight = game['memory'].get('imgHeight', 270)
# Pixel size of generated OIDs
pixelSize = game['memory'].get('pixelSize', 2)
# DPI of generated OIDs
dpi = game['memory'].get('dpi', 1200)
# The output yaml file
outputFile = game['memory'].get('outputFile', args.template.replace('.yaml', '-generated.yaml'))
# The output image file
outputImage = game['memory'].get('outputImage', args.template.replace('.yaml', f'-{dpi}dpi-{pixelSize}mm.png'))
# Get the language prefix for instruction sound files
lang = game.get('language', 'en')
# Get the title
title = game['memory'].get('title', 'Memory')
del game['memory']

# Number of pairs/cards
numPairs = len(pairs)
numCards = numPairs * 2

# Max card size in mm, cards are downscaled to fit the chosen image size
maxCardSize = 50

if outputFile == args.template:
    print('ERROR: Output file and input file cannot have the same name.')
    sys.exit(1)
if outputImage == args.template:
    print('ERROR: Output image file and input file cannot have the same name.')
    sys.exit(1)

oidCacheDir = 'oid-cache'

# initialization: lay out the cards in order, and set the number of pairs to find
game['init'] = ' '.join([f'$c{x}:={x+1}' for x in range(numCards)]) + f' $remaining:={numPairs} $player:=1'

# return the sound name for the given card
def sound(card):
    if card <= numPairs:
        p = pairs[card - 1]
        if alternativeSounds:
            return f'{p}_a'
    else:
        p = pairs[numCards - card]
        if alternativeSounds:
            return f'{p}_b'
    return p

scripts = {}

# $busy register is used to prevent the user to take an action while some script is still executing
# The 'idle' script allows clearing the busy state; clearing it in a separate script makes sure it is cleared at the end of any play command
scripts['idle'] = '$busy:=0'

# Player fields:
for p in range(1, players+1):
    scripts[f'p{p}'] = [
        # Choose number of players at the beginning of the game & initialize $random
        f'$players==0? $players:={p} $busy:=1 T($random, 65535) J(shuffle) P({lang}_shuffle)',
        # Remind that this player is not playing
        f'$busy==0? $players<{p}? $busy:=1 J(idle) P({lang}_not_playing)'
        # Speak out the number of pairs of the given player during the game (and when its finished)
        ] + [f'$busy==0? $pairs{p}=={pa}? $busy:=1 J(idle) P({lang}_pairs{pa})' for pa in range(numPairs+1)]

# Question mark field:
# Check game started
question = [f'$busy==0? $players==0? $busy:=1 J(idle) P({lang}_not_started)']
# Tell which players turn it is (if the game is still ongoing)
question += [f'$busy==0? $remaining>0? $player=={p}? $busy:=1 J(idle) P({lang}_player{p})' for p in range(1, players+1)]
# Tell who is the winner
for player in range(1, players+1):
    compare = '$busy==0? '
    for other in range(1, players+1):
        if player != other:
            compare += f'$pairs{player}>$pairs{other}? '
    question.append(compare + f'$busy:=1 J(idle) P({lang}_winner{player})')
# Else: there are multiple winners
question.append(f'$busy==0? $busy:=1 J(idle) P({lang}_draw)')
scripts['q'] = question

# Restart game if finished, else repeat last card again: This can be useful if there was some noise and the card wasn't heard by someone.
# But it won't help if in addition all players forgot which card has been tipped :-)
# (The coordinates of the last card could be read out in addition, but that just get's too complicated.)
scripts['r'] = [f'$busy==0? $remaining==0? $busy:=1 J(restart0) P(nop)'] + [f'$busy==0? $lastCard=={c}? $busy:=1 J(idle) P({sound(c)})' for c in range(1, numCards+1)]

# Shuffle the cards
# Start by computing $pos where the 1st card shall be moved
scripts['shuffle'] = f'$random*=25173 $random+=13849 $rnd:=$random $pos:=$rnd $pos%={numCards} $rnd/={numCards} J(shuffle0) P(nop)'
# The first loop iterates over all positions
for pos1 in range(numCards-1):
    l = []
    if pos1 < numCards-2:
        # Special case: when $rnd becomes too small, generate a new random number and repeat this script
        # (this must be done in a separate step to not end up with more than 8 commands per line; for the same reason $rnd is used multiple times; but it can be skipped in the last step)
        l.append(f'$rnd<{10 * (numCards-pos1-1)}? $random*=25173 $random+=13849 $rnd:=$random J(shuffle{pos1}) P(nop)')

    # The second loop iterates over the current field to the end, to chose to which place the current card shall be moved.
    for pos2 in range(pos1, numCards):
        swap = f'$pos=={pos2-pos1}? '
        if pos1 != pos2: # swap cards on pos1 and pos2
            swap += f'$t:=$c{pos1} $c{pos1}:=$c{pos2} $c{pos2}:=$t '
        if pos1 == numCards-2: # -2 because shuffle of the last card (numCards-1) is skipped because there is no other position available for that card
            # After last shuffle start the game
            swap += f'P({lang}_start) J(idle) P({lang}_player1)'
        else:
            # Compute pos where to move the next card and jump to the next shuffle step
            swap += f'$pos:=$rnd $pos%={numCards-pos1-1} $rnd/={numCards-pos1-1} J(shuffle{pos1+1}) P(nop)'
        l.append(swap)
    scripts[f'shuffle{pos1}'] = l

# The cards:
for c in range(numCards):
    scripts['c{}'.format(c)] = [
        # Game is not yet started
        f'$players==0? P({lang}_not_started)',
        # Game is already finished
        f'$remaining==0? P({lang}_finished)',
        # Chosen field is already empty - something that cannot happen in the real memory :-): be nice and let the player chose another field
        f'$busy==0? $c{c}==0? $busy:=1 J(idle) P({lang}_empty)',
        # Player choses a 1st card ($busy must be checked to make sure the player cannot re-chose another 1st card while the 2nd card is being processed)
        f'$busy==0? $card1==0? $card1:=$c{c} $pos1:={c} $lastCard:=$c{c} $lastPos:={c} $busy:=1 J(firstCard) P(nop)',
        # Player tips agan on the 1st card, replay its sound
        f'$busy==0? $card1==$c{c}? $busy:=1 J(firstCard) P(nop)',
        # Player choses a 2nd card ($busy is checked and set to make sure the player cannot re-chose another 2nd card while the card is being read out)
        f'$busy==0? $card1!=$c{c}? $card2:=$c{c} $pos2:={c} $lastCard:=$c{c} $lastPos:={c} $busy:=1 J(secondCard) P(nop)'
    ]

# Read out first card
scripts['firstCard'] = [f'$card1=={c}? J(idle) P({sound(c)})' for c in range(1, numCards+1)]

# Read out second card & test for a match
scripts['secondCard'] = [f'$card2=={c}? $sum:=$card1 $sum+=$card2 $card1:=0 $card2:=0 J(test) P({sound(c)})' for c in range(1, numCards+1)]

# Test for matching cards: increase pairs of current player or move to next player
scripts['test'] = [f'$sum=={numCards+1}? $player=={p}? $pairs{p}+=1 $remaining-=1 J(clear1) P({lang}_match)' for p in range(1, players+1)] \
    + [f'$player==$players? $player:=1 J(idle) P({lang}_player1)'] + [f'$player=={p}? $player+=1 J(idle) P({lang}_player{p+1})' for p in range(1, players)]

# Check end of game condition, else remove the two cards (the last two cards are never removed from the board to save some jumps, but this does not matter)
scripts['clear1'] = [f'$remaining==0? $busy:=0 J(q) P({lang}_finished)'] + [f'$pos1=={c}? $c{c}:=0 $pos1:=0 J(clear2) P(nop)' for c in range(numCards)]
scripts['clear2'] = [f'$pos2=={c}? $c{c}:=0 $pos2:=0 J(idle) P({lang}_continue)' for c in range(numCards)]

# Restart the game:
# Find all variables and their initial value
regex = re.compile(r'\$([a-zA-Z0-9]+):=([0-9]+)')
variables = {}
for a in regex.findall(game['init']):
    variables[a[0]] = a[1]
regex = re.compile(r'\$([a-zA-Z0-9]+)')
for script in scripts.values():
    for line in script:
        for o in regex.findall(line):
            if not o in variables:
                variables[o] = 0
# $busy is cleared separatly through J(idle) at the end
del variables['busy']

# Produce a list of scripts to reset the variables (to not have more than 8 commands)
count = 0
cmd = ''
i = 0
for variable in variables.items():
    if count == 6:
        scripts[f'restart{i}'] = cmd + f'J(restart{i+1}) P(nop)'
        i += 1
        count = 0
        cmd = ''
    count += 1
    cmd += f'${variable[0]}:={variable[1]} '
scripts[f'restart{i}'] = cmd + f'J(idle) P({game["welcome"]})'

game['scripts'] = scripts

# Generate speak entries for the cards in case there are none already present
speak = game.get('speak', [])
for p in pairs:
    if alternativeSounds:
        if not f'{p}_a' in speak:
            speak[f'{p}_a'] = p
        if not f'{p}_b' in speak:
            speak[f'{p}_b'] = p
    else:
        if not p in speak:
            speak[p] = p

# Remove all speak entries that already have an audio file
mediaPath = game.get('media-path', 'media/%s')
for s in list(game['speak']):
    for ext in ['.wav', '.ogg', '.flac', '.mp3']:
        audioFile = mediaPath.replace('%s', s + ext)
        if os.path.isfile(audioFile):
            del game['speak'][s]
            break
if len(speak) == 0:
    # Remove speak when there are no missing audio files
    del game['speak']
else:
    game['speak'] = speak
    print(f'{len(speak)} audio files are missing: {", ".join(speak)}')

# Generating scriptcodes (use deterministic codes for the p, q, r & c fields to be able to reuse already printed memory layouts)
codes = {}
if 'scriptcodes' in game:
    codes = game['scriptcodes']

# Question, Repeat & Player fields
code = 2000
if not 'q' in codes:
    codes['q'] = code
code += 1
if not 'r' in codes:
    codes['r'] = code
for p in range(players):
    code += 1
    script = f'p{p+1}'
    if not script in codes:
        codes[script] = code

# Cards
code = 3000
for c in range(numCards):
    script = f'c{c}'
    if not script in codes:
        codes[script] = code
    code += 1

# Add all other scripts
code = 4000
for script in scripts:
    if not script in codes:
        codes[script] = code
        code += 1

game['scriptcodes'] = codes


if args.play:
    # Remove P(nop) commands and flip any J(m) P(m) into P(m) J(m)
    # This makes the yaml file suitable for the "tttool play" that currently executes only the last P(m) if there are multiple J(m) P(m) in succession
    nop = re.compile(r' P\(nop\)')
    jump = re.compile(r'(J\([^\)]+\)) (P\([^\)]+\))')
    for s in scripts:
        if type(scripts[s]) == list:
            scripts[s] = [jump.sub(r'\2 \1', nop.sub('', l)) for l in scripts[s]]
        else:
            scripts[s] = jump.sub(r'\2 \1', nop.sub('', scripts[s]))

with open(outputFile, 'w') as f:
    data = yaml.dump(game, f, allow_unicode=True, width=1000)
print(f"Generated file: {outputFile}")

def check_tttool():
    if not os.path.isfile(tttool):
        fatalError(f'tttool executable not found at {tttool}. Please copy/link the tttool to this location or specify the correct path in the tttool variable.')

if args.play:
    check_tttool()
    subprocess.run([tttool, "play", outputFile])
    sys.exit(0)
else:
    check_tttool()
    subprocess.run([tttool, "assemble", outputFile], check=True)
    print(f"Generated file: {outputFile.replace('.yaml', '.gme')}")

if args.yml_only:
    sys.exit(0)

# Produce Game Board
def mm2px(mm):
    return int(mm * dpi / 25.4)

margin = dpi/6
width = mm2px(imgWidth)
height = mm2px(imgHeight)

yTitle = mm2px(10)
ySubtitle = yTitle + mm2px(10)
yHeader = ySubtitle + mm2px(10)
yCards = yHeader + mm2px(30)

# determine circle size to fit players + 3 cricles in a row on the page
circleSize = min(mm2px(25), int(width / (players + 3) * 0.95))

w = width
h = height - yCards

rows = 0
cols = 0
size = 0
# Search for the card layout that allows for the largest cards:
for c in range(1, numCards+1):
    r = math.ceil(numCards / c)
    # chose size by filling horizontally
    s = int((w - (c-1) * margin) / c)
    # check if it fits & is better
    if r * s + (r-1) * margin <= h and s >= size:
        size = s
        rows = r
        cols = c
    # chose size by filling vertically
    s = int((h - (r-1) * margin) / r)
    # check if it fits & is better
    if c * s + (c-1) * margin <= w and s >= size:
        size = s
        rows = r
        cols = c

# maxCardSize in pixels:
maxSize = int(maxCardSize * dpi / 25.4)
if size > maxSize:
    size = maxSize

# create cache dir for OID png files
if not os.path.exists(oidCacheDir):
    os.mkdir(oidCacheDir)
elif not os.path.isdir(oidCacheDir):
    print(f'ERROR: "{oidCacheDir}" is not a directory')
    sys.exit(1)

img = Image.new('RGBA', (width, height), 'white')
draw = ImageDraw.Draw(img)

def centerText(x, y, msg, font, color):
    w, h = draw.textsize(msg, font=font)
    w2, h2 = font.getoffset(msg) # todo: is this a bug or really needed? Seems to depend on the font
    w += w2
    h += h2
    draw.text((x-w/2, y-h/2), msg, fill=color, font=font)

def drawOid(oid, x, y, size, round=True):
    # check if OID file already exists
    path = f'{oidCacheDir}/oid-{oid}-{dpi}dpi-{pixelSize}px.png'
    if not os.path.isfile(path):
        # generated OID file
        subprocess.run([tttool, "--code-dim", str(maxCardSize), '--pixel-size', str(pixelSize), '--dpi', dpi, "oid-code", str(oid)], check=True)
        os.rename(f'./oid-{oid}.png', path)
    # open and draw the image
    oidImg = Image.open(path).crop((0, 0, size+1, size+1)).convert("RGBA")
    if round:
        # Create a round alpha channel to keep only a circle
        alpha = oidImg.getchannel('A')
        black = Image.new('L', (size+1, size+1), color='black')
        circle = Image.new('L', (size+1, size+1), color='white')
        ImageDraw.Draw(circle).ellipse([0, 0, size+1, size+1], fill='black')
        alpha.paste(black, (0,0), circle)
    else:
        alpha = oidImg
    img.paste(oidImg, (x, y), alpha)

def drawScriptOid(oidName, x, y, size, round=True):
    drawOid(codes[oidName], x, y, size, round)

# Add title & subtitle
font = ImageFont.truetype('Courier', int(dpi / 2))
centerText(width/2, yTitle, title, font, 'black')
font = ImageFont.truetype('Courier', int(dpi / 8))
centerText(width/2, ySubtitle, f'Id: {game["product-id"]}, {dpi}dpi, {pixelSize}mm', font, 'lightgray')

# Draw header line
font = ImageFont.truetype('Courier', int(dpi * 3 / 4))
color = 'lightgray'
m = (w - (players + 3) * circleSize) / (players + 2)
lineWidth = int(dpi/20)
for c in range(players + 3):
    x = int(c * (circleSize + m))
    draw.arc([x, yHeader, x+circleSize+1, circleSize+1+yHeader], start=0, end=360, fill=color, width=int(dpi/60))
    if c == 0:
        # Draw start symbol
        d = circleSize / 5
        draw.arc([d, d + yHeader, circleSize-d+1, circleSize-d+1 + yHeader], start=-30, end=210, fill=color, width=lineWidth)
        draw.line([circleSize / 2, circleSize / 4 + yHeader, circleSize / 2, circleSize * 3/5 + yHeader], fill=color, joint="curve", width=lineWidth)
        drawOid(game['product-id'], x, yHeader, circleSize)
    elif c <= players:
        centerText(x + circleSize / 2, circleSize / 2 + yHeader, str(c), font, color)
        drawScriptOid(f'p{c}', x, yHeader, circleSize)
    elif c == players + 1:
        centerText(x + circleSize / 2, circleSize / 2 + yHeader, '?', font, color)
        drawScriptOid('q', x, yHeader, circleSize)
    else:
        # Draw repeat symbol
        d = circleSize / 5
        draw.arc([x + d, d + yHeader, x + circleSize-d+1, circleSize-d+1 + yHeader], start=0, end=270, fill=color, width=lineWidth)
        draw.polygon([(x + circleSize/2, d/2+lineWidth/2 + yHeader), (x + circleSize/2 + d*2/3, d+lineWidth/2 + yHeader), (x + circleSize/2, d*3/2+lineWidth/2 + yHeader)], fill=color)
        drawScriptOid('r', x, yHeader, circleSize)

# Draw cards
cardWidth = (w - cols * size - (cols-1) * margin) / 2
for r in range(rows):
    for c in range(cols):
        if c + r * cols < numCards:
            y = int(r * (size + margin) + yCards)
            x = int(c * (size + margin) + cardWidth)
            draw.rectangle([x, y, x+size+1, y+size+1], outline='black', width=20)
            drawScriptOid(f'c{r * cols + c}', x, y, size, round=False)

# We're done!
img.save(outputImage, dpi=(dpi, dpi))
print(f'Generated file: {outputImage}')
