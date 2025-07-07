import argparse
import configparser
import os
import sys

from .manager import Manager
from .config import Config
from .logger import logger


CONFIG_PATH = Config.CONFIG_PATH


def load_config():
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_PATH):
        config.read(CONFIG_PATH)
    return config

def save_config(config):
    with open(CONFIG_PATH, 'w') as configfile:
        config.write(configfile)

def get_setting(args):
    config = load_config()
    if args.section in config and args.key in config[args.section]:
        logger(f"{args.key} = {config[args.section][args.key]}")
    else:
        logger(f"Setting {args.section}.{args.key} not found")

def set_setting(args):
    config = load_config()
    if args.section not in config:
        config[args.section] = {}
    config[args.section][args.key] = args.value
    save_config(config)
    logger(f"Setting {args.section}.{args.key} = {args.value}")

def set_defaults(config):
    for key, value in Config.__dict__.items():
        if key.isupper() and not key.startswith("__"):
            config[key] = str(value)

def run_maintenance(args):
    config = load_config()
    # Update Config with values from config file
    for section in config.sections():
        for key, value in config[section].items():
            setattr(Config, key.upper(), value)
    
    manager = Manager()
    manager.run_maintenance()

def main():
    parser = argparse.ArgumentParser(description="rTorrent Manager")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Get setting command
    get_parser = subparsers.add_parser("get", help="Get a setting")
    get_parser.add_argument("section", help="Section of the setting")
    get_parser.add_argument("key", help="Key of the setting")
    get_parser.set_defaults(func=get_setting)

    # Set setting command
    set_parser = subparsers.add_parser("set", help="Set a setting")
    set_parser.add_argument("section", help="Section of the setting")
    set_parser.add_argument("key", help="Key of the setting")
    set_parser.add_argument("value", help="Value of the setting")
    set_parser.set_defaults(func=set_setting)

    # Run maintenance command
    maintenance_parser = subparsers.add_parser("maintenance", help="Run maintenance tasks")
    maintenance_parser.set_defaults(func=run_maintenance)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()