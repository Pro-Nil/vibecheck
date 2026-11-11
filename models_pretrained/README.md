# Pretrained weights

`laion_aesthetic_vit_b_32.npz`: the LAION aesthetic predictor for CLIP ViT-B/32 (a single linear layer, 512 → 1),
converted from `sa_0_4_vit_b_32_linear.pth` in https://github.com/LAION-AI/aesthetic-predictor (MIT licence).
It rates general visual appeal on a 1–10 scale from human ratings. VibeCheck uses it only as "audience appeal"
for the likes prediction, never for the on-brand verdict (it rated the team's rejected drafts higher than the accepted posters).
