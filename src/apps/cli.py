import argparse
import json
import os
import re
import subprocess as sp
import sys
import tempfile


with open (os.environ.get("translatorsJsonFile")) as f:
  translators = json.load(f)


def strip_hashes_from_lock(lock):
  for source in lock['sources'].values():
    del source['hash']


def list_translators(args):
  out = "Available translators per build system"
  for subsystem, trans_types in translators.items():
    displayed = []
    for trans_type, translators_ in trans_types.items():
      for trans_name, translator in translators_.items():
        lines = tuple(
          f"{trans_type}.{trans_name}",
        )
        if translator:
          lines += (
            f"\n      special args:",
          )
          for argName, argData in translator.items():
            lines += (
              f"\n        --arg_{argName} {{value}}",
              f"\n            default: {argData['default']}",
              f"\n            examples: {', '.join(argData['examples'])}",
            )
        displayed.append(''.join(lines))
    nl = '\n'
    out += f"\n\n  - {subsystem}.{f'{nl}  - {subsystem}.'.join(displayed)}"
  print(out)


def translate(args):

  dream2nix_src = os.environ.get("dream2nixSrc")

  inputPaths = args.input

  # collect special args
  specialArgs = {}
  for argName, argVal in vars(args).items():
    if argName.startswith("arg_"):
      specialArgs[argName[4:]] = argVal

  # check if all inputs exist
  for path in inputPaths:
    if not os.path.exists(path):
      raise Exception(f"Input path '{path}' does not exist")

  inputFiles = list(filter(lambda p: os.path.isfile(p), inputPaths))
  inputDirectories = list(filter(lambda p: os.path.isdir(p), inputPaths))

  # determine output directory
  if os.path.isdir(args.output):
    output = f"{args.output}/dream.lock"
  else:
    output = args.output
  output = os.path.realpath(output)

  # translator arguments
  translatorInput = dict(
    inputFiles=inputFiles,
    inputDirectories=inputDirectories,
    outputFile=output,
    selector=args.translator or "",
  )
  translatorInput.update(specialArgs)

  # remove output file if exists
  if os.path.exists(output):
    os.remove(output)

  # dump translator arguments to json file and execute translator
  with tempfile.NamedTemporaryFile("w") as inputJsonFile:
    json.dump(translatorInput, inputJsonFile, indent=2)
    inputJsonFile.seek(0) # flushes write cache
    env = os.environ.copy()
    env.update(dict(
      FUNC_ARGS=inputJsonFile.name
    ))
    procEval = sp.run(
      [
        "nix", "eval", "--impure", "--raw", "--expr",
        f"((import {dream2nix_src} {{}}).translators.selectTranslatorJSON {{}})",
      ],
      capture_output=True,
      env=env
    )
    if procEval.returncode:
      print("Selecting translator failed", file=sys.stdout)
      print(procEval.stderr.decode(), file=sys.stderr)
      exit(1)

    # parse data for auto selected translator
    resultEval = json.loads(procEval.stdout)
    subsystem = resultEval['subsystem']
    trans_type = resultEval['type']
    trans_name = resultEval['name']

    # include default values into input data
    translatorInputWithDefaults = resultEval['SpecialArgsDefaults']
    translatorInputWithDefaults.update(translatorInput)
    json.dump(translatorInputWithDefaults, inputJsonFile, indent=2)
    inputJsonFile.seek(0)

    # build the translator bin
    procBuild = sp.run(
      [
        "nix", "build", "--impure", "-o", "translator", "--expr",
        f"(import {dream2nix_src} {{}}).translators.translators.{subsystem}.{trans_type}.{trans_name}.translateBin",
      ],
      capture_output=True,
    )
    if procBuild.returncode:
      print("Building translator failed", file=sys.stdout)
      print(procBuild.stderr.decode(), file=sys.stderr)
      exit(1)

    # execute translator
    translatorPath = os.path.realpath("translator")
    os.remove("translator")
    sp.run(
      [f"{translatorPath}/bin/translate", inputJsonFile.name] + sys.argv[1:]
    )

  # raise error if output wasn't produced
  if not os.path.isfile(output):
    raise Exception(f"Translator failed to create dream.lock")

  # read produced lock file
  with open(output) as f:
    lock = json.load(f)

  # calculate combined hash
  if args.combined:

    print("Start building FOD for combined sources to get output hash")

    # remove hashes from lock file and init sourcesCombinedHash with emtpy string
    strip_hashes_from_lock(lock)
    lock['generic']['sourcesCombinedHash'] = ""
    with open(output, 'w') as f:
      json.dump(lock, f, indent=2)

    # compute FOD hash of combined sources
    proc = sp.run(
      [
        "nix", "build", "--impure", "-L", "--expr",
        f"(import {dream2nix_src} {{}}).fetchSources {{ genericLock = {output}; }}"
      ],
      capture_output=True,
    )

    # read the output hash from the failed build log
    match = re.search(r"FOD_PATH=(.*=)", proc.stderr.decode())
    if not match:
      print(proc.stderr.decode())
      print(proc.stdout.decode())
      raise Exception("Could not find FOD hash in FOD log")
    hash = match.groups()[0]
    print(f"Computed FOD hash: {hash}")

    # store the hash in the lock
    lock['generic']['sourcesCombinedHash'] = hash
    with open(output, 'w') as f:
      json.dump(lock, f, indent=2)
    

  print(f"Created {output}")


def parse_args():

  parser = argparse.ArgumentParser(
    prog="nix run dream2nix --",
    # description="translate projects to nix",
  )

  sub = parser.add_subparsers(
    title='actions',
    description='valid actions',
    help='which action to execute'
  )

  list_parser = sub.add_parser(
    "list",
    description="list available translators"
  )

  list_parser.set_defaults(func=list_translators)


  # PARSER FOR TRNASLATOR

  translate_parser = sub.add_parser(
    "translate",
    prog="translate",
    description="translate projects to nix",
  )

  translate_parser.set_defaults(func=translate)

  translate_parser.add_argument(
    "-t", "--translator",
    help="select translator (list via: 'dream2nix list')",
    default=""
  )

  translate_parser.add_argument(
    "-o", "--output",
    help="output file/directory for the generic lock",
    default="./dream.lock"
  )

  translate_parser.add_argument(
    "-c", "--combined",
    help="Store only one hash for all sources combined (smaller lock file -> larger FOD)",
    action="store_true"
  )

  translate_parser.add_argument(
    "input",
    help="input files or directories containing sources and metadata",
    nargs="+"
  )

  # parse special args
  # (custom parameters required by individual translators)
  parsed, unknown = translate_parser.parse_known_args()
  for arg in unknown:
    if arg.startswith("--arg_"):
      translate_parser.add_argument(arg.split('=')[0])

  args = parser.parse_args()

  if not hasattr(args, "func"):
    parser.print_help()
    exit(1)

  args.func(args)


def main():

  args = parse_args()


if __name__ == "__main__":
  main()
