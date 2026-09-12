/**
 * The social dog mark, as SVG so it stays crisp at every size and can be
 * recoloured from CSS. Geometry follows the app icon: floppy ears behind a
 * round head, sunglasses across the eyes, cream muzzle, tongue out.
 *
 * `plate` draws the black squircle behind the dog (the app-icon form). Without
 * it the dog sits transparently on whatever is behind it, which is what the
 * in-page header wants.
 */
export function SocialDogLogo({
  size = 40,
  plate = false,
  className,
}: {
  size?: number;
  plate?: boolean;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 1280 1280"
      className={className}
      role="img"
      aria-label="social dog"
      fill="none"
    >
      {plate && <rect width="1280" height="1280" rx="300" fill="#000000" />}

      {/* ears, behind the head */}
      <rect x="265" y="320" width="155" height="370" rx="77" fill="#A6632B" />
      <rect x="860" y="320" width="155" height="370" rx="77" fill="#A6632B" />

      {/* head */}
      <ellipse cx="640" cy="472" rx="248" ry="225" fill="#C6843F" />

      {/* sunglasses: temple arms, then bridge, then the two lenses */}
      <rect x="352" y="440" width="90" height="34" rx="17" fill="#171310" />
      <rect x="838" y="440" width="90" height="34" rx="17" fill="#171310" />
      <rect x="608" y="440" width="74" height="34" rx="17" fill="#171310" />
      <rect x="424" y="396" width="198" height="144" rx="54" fill="#171310" />
      <rect x="668" y="396" width="198" height="144" rx="54" fill="#171310" />
      {/* lens glint */}
      <ellipse cx="478" cy="452" rx="21" ry="33" transform="rotate(-20 478 452)" fill="#FAECCB" />

      {/* tongue, tucked under the muzzle */}
      <rect x="600" y="640" width="80" height="172" rx="40" fill="#FF5C78" />

      {/* muzzle and nose */}
      <ellipse cx="640" cy="600" rx="122" ry="80" fill="#FAECCB" />
      <ellipse cx="640" cy="585" rx="43" ry="31" fill="#2B1B0C" />
    </svg>
  );
}

/** Logo plus the two-tone wordmark, for page headers. */
export function SocialDogWordmark({ size = 40 }: { size?: number }) {
  return (
    <span className="sd-brand">
      <SocialDogLogo size={size} />
      <span className="sd-wordmark">
        social <span className="sd-wordmark-accent">dog</span>
      </span>
    </span>
  );
}
