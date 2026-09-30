# BMB Veterinary Hospital website

Django website for BMB Veterinary Hospital & 24 Hrs Emergency Service.
All page content is edited through the staff dashboard at `/dashboard/`.

## Getting started

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python manage.py migrate
python manage.py seed_site          # loads the hospital's details and starter content
python manage.py createsuperuser    # login for /dashboard/
python manage.py runserver
```

The site runs at http://127.0.0.1:8000/ and the dashboard at http://127.0.0.1:8000/dashboard/.
Django's own admin is still available at http://127.0.0.1:8000/admin/ for managing users and permissions.

`seed_site` can be run again at any time. It only adds what is missing and never
overwrites content that has been edited in the admin.

## Project layout

```
config/                 Project configuration
  settings/
    base.py             Settings shared by every environment
    dev.py              Local development (the default for manage.py)
    prod.py             Production (the default for wsgi.py / asgi.py)
  urls.py
apps/
  core/                 Site settings, home and about pages, hero slides, statistics
  services/             Services list and detail pages
  team/                 Team list and profile pages
  pricing/              Price list
  faq/                  Frequently asked questions
  gallery/              Photo gallery
  testimonials/         Client testimonials shown on the home page
  contact/              Contact form and received messages
  accounts/             Staff users, roles and "My profile"
  clinic_setup/         Species, history options, vaccination types, examination types
  clients/              Pet owners and their pets, with client and pet record pages
  appointments/         Walk-in queue, consultations, follow-ups and printable visit summaries
  shop/                 Products, stock and the public pet shop pages
  billing/              Invoices for counter sales and visits, and payments
  dashboard/            Staff dashboard: layout, sign-in, and the list and form pages for every module
templates/              Page templates, one folder per app, shared pieces in partials/
static/                 CSS, JavaScript and the logo
media/                  Files uploaded through the admin
```

## Editing content

| What | Where in the dashboard |
| --- | --- |
| Register a walk-in, see who is waiting | Clinic > Today's queue |
| Every visit, searchable by date, status, vet or phone | Clinic > Appointments |
| Owners and pets, with their full records | Clinic > Clients, Clinic > Pets |
| Lists used during visits | Clinic setup |
| Sell at the counter, bill a visit, take payments | Billing > New sale, Billing > Invoices |
| Products, prices and stock | Shop > Products, Shop > Stock history |
| Staff logins and what each role can do | Staff > Staff users, Staff > Roles |
| Phone, WhatsApp, email, address, social links, map, about text | Website > Site settings |
| Home page slider | Website > Hero slides |
| Numbers band | Website > Statistics |
| Services | Content > Services |
| Staff profiles and their experience | Content > Team members |
| Price list and its items | Content > Price categories |
| Questions and answers | Content > FAQ categories and FAQs |
| Photos | Content > Gallery images |
| Reviews | Content > Testimonials |
| Messages sent from the website | Inbox > Contact messages |

Sections with no content hide themselves. For example, the testimonials and team
sections appear on the home page once the first entry is added.

The logo is `static/images/bmb.jpg`. Replace that file to change it.

## Dashboard

Staff sign in at `/dashboard/`. Staff accounts are created under **Staff > Staff users**,
each with one role. A role decides what that person can see and do; roles are edited
under **Staff > Roles** by ticking permissions. Superusers can always do everything.

Three roles are created automatically when you run `migrate`:

| Role | Can do |
| --- | --- |
| Administrator | Everything, including staff, roles, clinic setup and the website |
| Veterinarian | Clients, pets and appointments, including history, examination, treatment and result; can reopen completed visits |
| Receptionist | Registers owners, pets and walk-ins and manages the queue; does not see clinical details |

After they are created, changes you make to a role are kept. The Administrator role
automatically gets permissions for any new module.

### Adding a module for a new app

Each app describes its own modules in a `dashboard.py` file, which the dashboard
finds automatically. For a new app with a `Vaccine` model:

```python
# apps/vaccines/dashboard.py
from apps.dashboard.registry import Module, site

from .models import Vaccine


@site.register(Vaccine)
class VaccineModule(Module):
    group = "Content"              # heading in the side menu
    icon = "ki-syringe"            # any Keenicons outline icon
    description = "Vaccines offered by the hospital."
    list_display = ["name", "price", "is_active"]
    search_fields = ["name"]
    list_filter = ["is_active"]
    toggle_fields = ["is_active"]  # switched on and off from the list
```

That gives the model a menu entry, a count on the dashboard home page, and list,
add, edit and delete pages. Other options are documented in
`apps/dashboard/registry.py`: `fields`, `inlines` (child rows edited on the parent's
form), `singleton`, `can_add`, `can_change`, `can_delete`, `ordering` and `per_page`.

### Theme

The dashboard uses the Metronic theme. Only the files it needs are kept, in
`apps/dashboard/static/dashboard/`. The `demo1/` folder is the full reference copy
of the theme; it is not used at runtime and is left out of version control.
Brand colours are set in `apps/dashboard/static/dashboard/css/dashboard.css`.

## Appointments

All visits are walk-ins:

1. **Register a walk-in** (Today's queue > New walk-in). Find the owner by name or
   phone, or add a new one, then pick one of their pets or add a new one. The visit
   joins today's queue with the next token number; tokens restart at 1 each day.
2. **Start the consultation.** The visit page has tabs for the visit, history,
   examination, vaccination, and treatment and result. The pet's allergies and alerts
   are shown at the top of every tab.
3. **Complete** the visit. Completed visits can then only be changed by someone
   allowed to edit completed appointments (Veterinarian and Administrator by default).
4. **Follow-ups:** setting a follow-up date offers "Create follow-up", which books a
   scheduled visit for that day. When the pet arrives, "Check in" gives it a token.

Every visit follows the hospital's registration form: Patient's History, Vaccination
Record and Clinical Examination. Administrators decide the fields in each section
under **Clinic setup** (History fields, Examination fields, Vaccination types): add,
rename, reorder or retire them, and choose each field's value type (number, choice
from a list, yes/no or free text) and what counts as normal. Every visit then lists
all fields in use, and staff only fill in the values; values outside normal are
flagged. Each field shows the pet's last recorded value, and the pet's record has a
Clinical history table of every value across visits.

The default fields match the paper form. **The normal ranges for temperature,
respiration, pulse and CRT are placeholders; confirm them with your vets before use.**
Vaccination types start without booster intervals; set them so the next due date is
suggested automatically.

**Printing:** "Print form" on a visit prints it on the two-page registration form
(registration, history, vaccination, examination and authorization, then treatment and
result) with the hospital's logo and details. "Blank form" on the queue prints an empty
one for owners to fill in by hand. The authorization paragraph is edited in
**Website > Site settings**.

Nothing clinical is ever shown on the public website.

## Shop and billing

**Products** (Shop > Products) are everything the hospital sells: medicines, food, toys,
cages, accessories, and clinic services such as the consultation fee. Services and
anything you don't count are saved with "Track stock" unticked. A new product can be
given an opening stock; after that, stock is changed only from its **Stock** page
(stock received, returned, damaged or a count correction) or by sales, and every change
is kept in Stock history. Products at or below their warning level are listed on the
dashboard home page.

To try things out, `python manage.py seed_shop` loads 46 sample products and services
(SKUs starting `SAMPLE-`, made-up prices and stock). `python manage.py seed_shop --remove`
deletes them again; any already sold are hidden instead, so past invoices stay intact.

**Selling:** every sale is an invoice.

- *Counter sale:* Billing > New sale. Pick a client, type a name and phone, or leave both
  blank for an anonymous sale. No appointment is needed.
- *Visit bill:* "Bill" in the queue, or "Create bill" on the visit page, starts a bill
  for the pet's owner linked to that visit.

Add items by searching products and services (their price fills in) or by typing a
description and price. A bill is a **draft** until you **issue** it: issuing takes the
items out of stock (refusing if there isn't enough), gives the invoice its number and
locks it. Take one or more payments (cash, card, eSewa, Khalti, Fonepay, bank) until it
is **paid**. An issued invoice is never deleted; cancelling it puts its items back in
stock. Print the invoice from its page.

Set the hospital's PAN/VAT number, default VAT rate and invoice footer under
**Website > Site settings**.

**Online shop:** products marked "Show in the online shop", in categories shown online,
appear at `/shop/` with their price. Visitors order by WhatsApp or phone and pick up at
the hospital; there is no online payment.

By default Veterinarians and Receptionists can bill and issue invoices, Receptionists
can also take payments, and only Administrators can adjust stock or cancel invoices.

## Running the tests

```powershell
python manage.py test apps
```

## Adding images in bulk

Images can be uploaded one at a time in the dashboard, or all at once: save them in
`seed_media/` under the file names listed in `seed_media/PROMPTS.md` and run
`python manage.py load_images`. That file also has a prompt for each image if
you are generating them with an AI tool.

## Production

Use `config.settings.prod` and set these environment variables:

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Required. A long random string. |
| `DJANGO_ALLOWED_HOSTS` | Required. Comma-separated host names. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated origins, e.g. `https://example.com`. |
| `CONTACT_NOTIFY_EMAIL` | Address that receives an email for each contact message. |
| `DEFAULT_FROM_EMAIL`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Outgoing mail. |

Then run `python manage.py migrate` and `python manage.py collectstatic`, and have
the web server serve `staticfiles/` and `media/`.
