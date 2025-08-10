{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShellNoCC {
  packages = with pkgs; [
    (python3.withPackages (ps: [
      ps.build
      ps.hatchling
      ps.jinja2
      ps.markupsafe
      ps.pip
    ]))

    yt-dlp
  ];
}
