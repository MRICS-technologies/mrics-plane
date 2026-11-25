/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import Link from "next/link";

// Stands in for the link while the sentence is translated, then splits it back out.
const LINK_SLOT = "\u0000";

type Props = {
  /** Translates the sentence with its `{link}` placeholder set to the given value. */
  translate: (link: string) => string;
  /** The link's own translated text. */
  linkLabel: string;
  href: string;
};

/**
 * A translated sentence with an in-app link at its `{link}` placeholder, so each locale keeps its
 * own word order. A translation without the placeholder gets the link at the end.
 */
export function InlineLinkText(props: Props) {
  const { translate, linkLabel, href } = props;
  const [before, ...rest] = translate(LINK_SLOT).split(LINK_SLOT);

  return (
    <>
      {before}
      <Link href={href} className="text-accent-primary hover:underline">
        {linkLabel}
      </Link>
      {rest.join("")}
    </>
  );
}
