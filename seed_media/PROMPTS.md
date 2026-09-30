# Image prompts

Generate each image with any AI image tool, save it in this folder under the file
name shown (`.jpg`, `.jpeg`, `.png` or `.webp`), then run:

```powershell
python manage.py load_images            # fills empty image slots
python manage.py load_images --replace  # also overwrites images already set
```

Add this to the end of every prompt so the set looks consistent:

> Realistic photograph, soft natural light, clean and bright, navy blue and warm
> orange colour accents, shallow depth of field, no text, no logos, no watermark.

Check each result before using it. AI tools often get paws, eyes and hands wrong.

## Home page slider (landscape, 1920 x 1080)

The slider puts a dark blue tint and white text over these, so keep the subject
towards the right and avoid busy backgrounds.

| File name | Prompt |
| --- | --- |
| `hero-1` | A calm golden retriever and a ginger cat sitting side by side on a veterinary examination table in a bright modern animal hospital. |
| `hero-2` | The entrance of a modern veterinary hospital at night, warm light glowing from the windows, a person carrying a small dog towards the door. |
| `hero-3` | Close-up of a person's hands gently holding a dog's paw, soft blurred clinic background. |

## About page (portrait or square, 1200 x 1200)

| File name | Prompt |
| --- | --- |
| `about` | A happy dog and a cat resting together on a blanket, looking at the camera, plain light background. |
| `philosophy` | A small fluffy white dog being gently stroked by a person's hand, warm and comforting mood. |

## Services (landscape, 1200 x 800)

| File name | Prompt |
| --- | --- |
| `service-emergency-care` | A dog lying on a padded treatment table in a veterinary emergency room with medical equipment softly blurred behind it. |
| `service-critical-care` | A cat resting under a soft blanket in a clean veterinary recovery kennel, monitoring equipment blurred in the background. |
| `service-advanced-diagnostics` | A modern veterinary laboratory bench with a microscope and sample tubes, clean and well lit. |
| `service-veterinary-consultation` | A stethoscope resting beside a relaxed Labrador on an examination table in a bright consulting room. |
| `service-vaccines` | A healthy puppy sitting on an examination table next to a small vaccine vial and a vaccination record card. |
| `service-small-pets-care` | A rabbit and a guinea pig sitting together on a soft towel on an examination table. |

## Pricing (landscape, 1200 x 800)

| File name | Prompt |
| --- | --- |
| `pricing-1` | A dog and a cat sitting next to each other, plain light background. (Cats & Dogs) |
| `pricing-2` | A cute guinea pig and a rabbit, plain light background. (Small Animals) |

## Gallery

Files placed in `gallery/` are added to the gallery page, and the file name becomes
the caption (`reception-area.jpg` becomes "Reception area").

The gallery is titled "Our Clinic", so visitors will take these as real photos of
the hospital. Use real photographs here rather than generated ones.
