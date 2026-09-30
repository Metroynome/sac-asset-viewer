# SAC extraction tools

These tools ship with the asset viewer. Python 3.10+ and its standard library are sufficient; no external extractor installation is needed.

The launcher runs `extract_sac.py` automatically. From the viewer repository, you can also run:

```bat
python -B tools/extract_sac.py "D:/PS2/ISOs/Secret Agent Clank.iso" --output "data/sac-extracted"
python -B tools/verify_sac.py "data/sac-extracted"
```

Use a new or empty output folder. The extractor dumps ISO files, extracts IMAGE.ZIP, decompresses HIG WADs, and verifies their checksums. The verifier compares saved data with the original ISO, checks hashes, and validates WAD section slices. Keep the original ISO available at the path recorded in the extraction manifest. Run verification without Python's `-O` flag, because the verifier uses assertions.

- `extract_sac.py`: ISO, ZIP, and WAD extraction.
- `archive_support.py`: ISO reader and checksum-validating TJZIP wrapper.
- `verify_sac.py`: extraction verification.
- `upstream/tjzip_dump.py`: unchanged upstream raw/dictionary token decoder.

## Attribution

The ISO reader and TJZIP wrapper were adapted from the project's Size Matters extraction tools. The token decoder is by electrogecko, from [UYA_pyTools / SM](https://github.com/electrogecko/UYA_pyTools/tree/main/SM). The original download recorded upstream commit `50565a903db30df775989031a4a7944515fb4126`. Its source is preserved unchanged in `upstream/tjzip_dump.py`; the SAC wrapper supplies the game-specific header and CRC handling.
