import * as LucideIcons from 'lucide-react';
import { Gift as GiftIcon } from 'lucide-react';

/**
 * Renders a gift icon from the lucide-react library by name.
 *
 * Falls back to the default Gift icon if the requested name is not found.
 *
 * Props:
 *   gift  - the gift object from the API. May include:
 *             - image_url     : custom uploaded image (preferred when present)
 *             - icon_name     : lucide-react icon component name (e.g. 'Heart')
 *             - icon_color    : hex color (e.g. '#EF4444')
 *   size  - icon size in px (default 32)
 *   color - override color (otherwise uses gift.icon_color or default)
 */
export function LucideGiftIcon({ gift, size = 32, color, style = {}, ...rest }) {
  if (!gift) {
    return <GiftIcon size={size} color={color || '#FFD700'} style={style} {...rest} />;
  }

  // Prefer uploaded image if admin uploaded one
  if (gift.image_url) {
    return (
      <img
        src={gift.image_url}
        alt={gift.name || 'gift'}
        width={size}
        height={size}
        style={{ objectFit: 'contain', ...style }}
        {...rest}
      />
    );
  }

  const iconName = gift.icon_name || 'Gift';
  const IconComponent = LucideIcons[iconName] || GiftIcon;
  const iconColor = color || gift.icon_color || '#FFD700';

  return <IconComponent size={size} color={iconColor} style={style} {...rest} />;
}

export default LucideGiftIcon;




