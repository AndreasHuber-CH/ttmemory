# ttmemory - An auditive memory game for the TipToi

This project contains a Memory Game generator for the TipToi pen. The memory game is played as usual, but each card will play a sound instead of showing a picture and you must find the two cards that produce the same sound.

If you just want to try it out, you can download the farm_animals_XX-generated.gme file in the language of your TipToi and print the corresponding png file.

Otherwise you can read through the doc to see how to generate your own memory game.

## Game Controls

The memory game board features a first row of round buttons that have the following function:

* Start Button
* Player Buttons
  * Used to chose the number of players at the beginning of the game
  * Read out the number of pairs the given player has found so far
* Question Button
  * Repeats which player's turn it is
  * Tells who won the game if it is finished
* Repeat Button
  * Repeats the last picked card in case someone didn't hear it (the 1st card can also be re-tipped again to repeat it, but the 2nd card can only be repeated with this button because the game advances immediately when the 2nd card is tipped)
  * Restarts the game if it is finished

Please be a bit patient while the TipToi shuffles the cards after you chose the number of players.

## Tips how to play the game

It turns out that an auditive memory is not that simple to play :-). The single most useful tip I can give is to use some coins or other objects to mark the two fields when a matching pair of cards is found - without that it will be hard to remember which fields are still available and which ones are already empty.

## Memory Generation Script

The memory.py script can generates a yaml that is then assembled into a gme file for the TipToi pen using tttool.
In a 2nd step it produces a png file with the corresponding game board. All the required OID codes are generated using tttool.

The memory.py script requires a yaml file as input.
This yaml file follows exactly the specification of tttool with an additional "memory" section.
By default all fields are copied over from the input to the output file.
The speak entries are automatically removed in the output file if an audio file with the same name is found (this allowed me gradually adding audio files while keeping all speak entries in the input file).

The custom "memory" section contains the following fields:

* pairs: List of names for the cards. There should be an audio file for each pair fo cards in the media directory. This is the only mandatory parameter.
* alternativeSounds: Default False. If set to true, two different sound files are played for each card in a pair. The sound files are named by appending "_a" and "_b" to the name of the pair.
* maxPlayers: Default 4. The max number of players that can play the memory game. (The number of players that effectively participate can be chosen at the beginning of each game.)
* imgWidth (in mm): Default 190. The width of the produced png file.
* imgHeight (in mm): Default 270. The height of the produced png file.
* pixelSize: Default 2. This value will be passed to tttool as --pixel-size parameter when generating the OIDs.
* dpi: Default 1200. This value will be passed to tttool as --dpi parameter when generating the OIDs. The generated game board png file uses the same dpi setting.
* outputFile: Name of the output file. If absent "-generated" is appended to the input file name.
* outputImage: Name of the generated png file. If absent it is constructed from the input file name, and the dpi and pixelSize parameters.
* title: Default "Memory". The title to print at the top of the png file.

I used the "alternativeSounds" option myself when I generated a memory game with the names of familymembers and relatives.
I let my two oldest kids speak the names and got so two different version for each name/card.

## Dependencies

The memory.py script is written in python3 and requires the following python modules (other than some more standard ones):

```bash
pip3 install pyyaml
pip3 install Pillow
```

Then tttool must be available. The script assumes it to be at "~/bin/tttool". You can either copy or link tttool to this place, or you can modify the memory.py script to change the path to tttool.

## Execution

The script can be executed in three modes:

```bash
./memory.sh farm_animals_de.yaml
./memory.sh -y farm_animals_de.yaml
./memory.sh -p farm_animals_de.yaml
```

The normal execution generates the yaml memory file, assembles it into a gme file and produces then the png game board.
The "-y" option skips the generation of the png game board (which is the slowest part).
The "-p" option generates a slightly modified version of the yaml memory file that better works with the tttool play mode and starts then the tttool play mode.

To make the memory game easier to try out in "tttool play" all OIDs that are printed on the game board have short names:

* "p1" - "pN" for the player fields
* "q" for the question mark field
* "r" for the repeat field
* "c0" - "cN" for the cards

## Caveats

I had some real issues with the TipToi pen that introduces some additional delay of almost 2 seconds whenever a command line ended with a J() command.
With the help from others on the tttool mailinglist I found out that this delay does not occur if the J() command is followed by a P() command (and the TipToi pen still plays out the P() command before jumping to the new script.)
The memory script makes heavily use of this. As an additional workaround I added a very short sound file, called "nop". And in any command line that has no P() command but requires a J() command I added a P(nop) after J(). This is not a perfect solution that still is not blazingly fast, which can be noticed when the cards are shuffled and a bunch of "nop" sounds are played, but it was the only way I could get it to work.

For printing, I ended up using 3mm pixel size instead of the 2mm default value used by tttool. I had better experience with it and that the fields become a bit gray does really not matter for the memory game.

## Acknowledgements

A big thank you goes to the creators of [tttool](https://github.com/entropia/tip-toi-reveng) - a really great tool!

Also thanks a lot for the nicely written [tttool book](https://tttool.readthedocs.io/de/latest/) that was my entry point and got me hooked with the idea to develop this memory game.
