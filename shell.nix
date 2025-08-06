{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShellNoCC {
  packages = with pkgs; [
    (python3.withPackages (ps: [
      ps.jinja2
      ps.markupsafe
    ]))
    yt-dlp
  ];
}
