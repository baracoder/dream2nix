{lib, ...}: let
  l = lib // builtins;
  t = l.types;
in {
  options = {
    functions.fetchers = {
      constructSource = l.mkOption {
        type = t.functionTo t.attrs;
      };
      updateSource = l.mkOption {
        type = t.functionTo t.attrs;
        description = ''
          update source spec to different version
        '';
      };
      fetchSource = l.mkOption {
        type = t.functionTo t.package;
        description = ''
          fetch a source defined via a dream lock source spec
        '';
      };
      fetchShortcut = l.mkOption {
        type = t.functionTo t.package;
        description = ''
          fetch a source defined by a shortcut
        '';
      };
      parseShortcut = l.mkOption {
        type = t.functionTo t.attrs;
      };
      translateShortcut = l.mkOption {
        type = t.functionTo t.attrs;
        description = ''
          translate shortcut to dream lock source spec
        '';
      };
    };
  };
}