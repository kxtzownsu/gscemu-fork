# gscemulator public release

## gscemu(lator), an emulator for the GSC(Google Security Chip(s))

powered by unicorn and python, gscemulator is able to run a production
copy of a gsc image!

## how to run
*running this as a module is not fully supported yet, as the imports may mess up
your system imports if you do not run it in a venv. to run without imports, run
`pip3 install -r requirements.txt && python3 main.py`*

`pip3 install git+https://github.com/HavenOverflow/gscemu && gscemu`

this was written 95% without AI, but one component within the emulator was \
still written with AI(timels.py). Removal and rewrite of this component is \
planned soon.

## how to use

GSCEmulator implements an interactive console over stdout to access the Cr50
console over UART. You may type in the console after running `gscemu`,
but you may need to wait for a while as it is booting. Precisely, the
```
Console is enabled; type HELP for help.
```
message.

## support

- haven
- citadel(TBC)
- dauntless(TBC)

### standard for devs

The python code written mostly follows the google style guide, with some
exceptions or changes here and there. \
    - 80 char ruler for python files \
    - functions use a standardized comment system \
    - all types and return values of functions should be already defined with `->` or `:`

This is not every standard that is used, but are the main standards that we
should use to write code.

### why are components in different files

originally, the purpose was to be able to swap components between different
chip types easily, but more and more that has gotten harder and harder to do due
to tight integration between many of the components. \
instead, now, the purpose of splitting them into files is for better code
readability.