# To do

## HACS shows no icon for the integration

Home Assistant shows the integration's icon (Settings → Devices & services),
but HACS shows a placeholder.

**Why:** since Home Assistant 2026.3, custom integrations ship their icons in
`custom_components/<domain>/brand/`
([developer blog](https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api)).
Ours are there and correct: `icon.png` (256×256), `icon@2x.png` (512×512) and
both logos, in every release since 0.1.0. HACS does not read that folder. It
still loads icons from brands.home-assistant.io, which has none for
`cfos_powerbrain`. Other integrations report the same
([hacs/integration#5171](https://github.com/hacs/integration/issues/5171),
[hacs/integration#5402](https://github.com/hacs/integration/issues/5402)).

**Not fixable here:**

- HACS itself will not get a fix: the pull request that would have served
  `brand/` icons was closed unmerged on 2026-10-16
  ([hacs/integration#5388](https://github.com/hacs/integration/pull/5388)),
  because HACS is moving into Home Assistant as the *Marketplace*
  integration.
- The brands repository's `custom_integrations` folder is legacy; new custom
  integration icons do not go there any more
  ([brands README](https://github.com/home-assistant/brands/blob/master/README.md)).
- The brands site's Marketplace path
  (`brands.home-assistant.io/marketplace/<domain>/icon.png`) serves icons
  from the integration's own repository, but only for repositories in the
  HACS default list (it reads `data-v2.hacs.xyz/integration/data.json`). This
  repository is added as a custom repository, so it is not included.

**To do:**

- [ ] After updating to Home Assistant 2026.11, check the icon in Marketplace.
      A HACS maintainer closed #5402 with "This is fixed in Marketplace, which
      ships with Home Assistant 2026.11". Unconfirmed: how Marketplace treats
      repositories added by URL rather than from the default list.
- [ ] If it is still missing, decide whether to submit the repository to the
      default list (check how submissions work now that HACS is Marketplace).
      That would also show the icon before installation.
- [ ] Optional, until then: a README note that HACS shows a placeholder icon.

## Due with Home Assistant 2026.11

- [ ] Add the manifest `categories` (`energy.ev_charging`,
      `energy.meters_monitoring`) once hassfest accepts them; see the README
      roadmap.
