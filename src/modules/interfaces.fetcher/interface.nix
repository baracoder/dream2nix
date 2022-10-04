{lib, ...}: let
  l = lib // builtins;
  t = l.types;

  outputsOptions = {
    options = {
      calcHash = l.mkOption {
        type = t.functionTo t.str;
        description = ''
          Function that will calculate the hash of the source.
          It should output the hash in the specified algo.
        '';
      };
      fetched = l.mkOption {
        type = t.functionTo t.package;
        description = ''
          Function that will output the source itself, given a hash.
        '';
      };
    };
  };
in {
  options = {
    inputs = l.mkOption {
      type = t.listOf t.str;
      description = ''
        The inputs that are passed to this fetcher.
      '';
    };
    versionField = l.mkOption {
      type = t.str;
      description = ''
        The name of an input that corresponds to the "version" of this source.
        This can be semantic versioning, a git revision, etc.
      '';
    };
    outputs = l.mkOption {
      type = t.functionTo (t.functionTo (
        t.submoduleWith {
          modules = [outputsOptions];
        }
      ));
    };
  };
}