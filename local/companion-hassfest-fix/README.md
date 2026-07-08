# Companion hassfest fix (ha-ipbuilding-gateway)

Fix for [Validate Home Assistant manifest #116](https://github.com/markminnoye/ha-ipbuilding-gateway/actions/runs/28914142812).

Replace `D<ch>` with `D{channel}` in service description strings so hassfest no longer treats `<ch>` as HTML.

Apply in the companion repo:

```bash
cd /path/to/ha-ipbuilding-gateway
git checkout -b cursor/fix-hassfest-d-channel-ec26
git am local/companion-hassfest-fix/ha-ipbuilding-gateway-hassfest-d-channel.patch
git push -u origin cursor/fix-hassfest-d-channel-ec26
```

Or copy the four files from `custom_components/ha_ipbuilding_gateway/` in this folder.
