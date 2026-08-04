import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { TextAreaField, TextField } from "@/components/ui/Field";
import { TagInput } from "@/components/ui/TagInput";
import { asList, asText, profileTitle } from "@/lib/profile";
import type { Profile } from "@/services/types";

/**
 * The parser's output is a starting point, not an answer. This is the manual
 * override: correct what it got wrong before running the match.
 *
 * The chat can edit the same fields in plain language, so both write back to
 * the same profile state and neither is authoritative over the other.
 */
export function ProfileForm({
  profile,
  onSubmit,
  busy,
}: {
  profile: Profile;
  onSubmit: (next: Profile) => void;
  busy: boolean;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [title, setTitle] = useState("");
  const [skills, setSkills] = useState<string[]>([]);
  const [experience, setExperience] = useState("");
  const [education, setEducation] = useState("");

  // Re-sync when the profile changes underneath: the chat agent returns a
  // whole updated profile, and the form has to follow it rather than holding
  // stale values the user thinks they already corrected.
  useEffect(() => {
    setName(asText(profile.name));
    setEmail(asText(profile.email));
    setPhone(asText(profile.phone));
    setTitle(profileTitle(profile));
    setSkills(asList(profile.skills));
    setExperience(asText(profile.experience));
    setEducation(asText(profile.education));
  }, [profile]);

  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit({ name, email, phone, title, skills, experience, education });
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="grid gap-5 sm:grid-cols-2">
        <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <TextField
          label="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          hint="Used for notifications only if you save it in Settings."
        />
        <TextField label="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
        <TextField
          label="Current or target title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>

      <TagInput
        label="Skills"
        hint="Remove anything wrong, or type to add what the parser missed. These drive retrieval."
        value={skills}
        onChange={setSkills}
      />

      <TextAreaField
        label="Experience"
        rows={5}
        value={experience}
        onChange={(e) => setExperience(e.target.value)}
      />
      <TextAreaField
        label="Education"
        rows={3}
        value={education}
        onChange={(e) => setEducation(e.target.value)}
      />

      <Button type="submit" loading={busy}>
        Confirm and find matches
      </Button>
    </form>
  );
}
