interface HciotHeroProps {
  eyebrow: string;
  title: string;
  description: string;
  note: string;
}

export default function HciotHero({
  eyebrow,
  title,
  description,
  note,
}: HciotHeroProps) {
  return (
    <section className="hciot-hero">
      <div className="hciot-hero-copy">
        <div className="hciot-eyebrow">{eyebrow}</div>
        <h2 className="hciot-hero-title">{title}</h2>
        <p className="hciot-hero-description">{description}</p>
      </div>
      <div className="hciot-hero-note">
        <div className="hciot-hero-note-label">Info</div>
        <p>{note}</p>
      </div>
    </section>
  );
}
