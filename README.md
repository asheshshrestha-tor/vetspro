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
  branches/             Branches, the branch switcher and the public Branches page
  accounts/             Staff users, roles, their branches and "My profile"
  clinic_setup/         Species, history and examination fields, vaccination types and plans,
                        treatment templates
  clients/              Pet owners and their pets, record pages and pet documents
  appointments/         Queue and triage board, bookings, consultations, follow-ups, vaccination plans
  schedules/            Doctors' weekly hours, leave and extra shifts, and who is available now
  shop/                 Products and packages, stock per branch, transfers, branch prices, pet shop pages
  billing/              Invoices for counter sales and visits, payments and receipts
  messaging/            Reminders and messages to owners by SMS, WhatsApp or email
  reports/              Sales, payments, visits and vets' work, with CSV export
  activity/             Log of changes and sign-ins
  dashboard/            Staff dashboard: layout, sign-in, and the list and form pages for every module
templates/              Page templates, one folder per app, shared pieces in partials/
static/                 CSS, JavaScript and the logo
media/                  Public uploads (photos for the website, product images)
private_media/          Pet documents: never served directly, only through the dashboard
```

## Editing content

| What | Where in the dashboard |
| --- | --- |
| Register a walk-in, see who is waiting | Clinic > Today's queue |
| Every visit, searchable by date, status, vet or phone | Clinic > Appointments |
| Doctors' weekly hours, leave and extra shifts | Clinic > Doctor schedule, Clinic > Leave & changes |
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

### Doctor schedule

**Clinic > Doctor schedule** shows the week for every doctor at the branch: regular
hours, extra shifts, leave and time away. Administrators set each doctor's regular week
with "Set hours" (up to two blocks a day, per branch; "Copy to weekdays" fills Tuesday to
Friday from Monday) and add leave, a few hours away or an extra shift under
**Clinic > Leave & changes**. Saving leave that falls on booked visits lists those visits
so they can be moved to another doctor or day.

The schedule is then used across the clinic:

- **Today's queue** shows each doctor's status: available, with a patient (and which
  one), later today, off duty, away or on leave, with how many pets are waiting for them.
  Click a doctor to see only their patients. The dashboard home shows the same list.
- **New walk-in / booking** shows each doctor's status for the chosen date in "Attended
  by". Choosing a doctor who is on leave, not working at the branch that day, or (for a
  booking with a time) outside their hours asks for "Keep this doctor" before saving.
  Moving a booking onto leave from the visit page shows a warning.
- **Bookings** shows who is on duty and who is on leave each day.

Doctors with no hours entered are shown as "Hours not set" and never trigger a warning,
so the schedule can be filled in one doctor at a time.

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

**Treatment catalogue** (Clinic setup > Treatment catalogue) lists the medicines,
procedures and advice vets pick in a visit's Treatment tab, each with its price and usual
dose, route, frequency and duration. Medicines in it are the same items as in the shop,
so they share one price and one stock count. Advice is usually priced 0 (not charged).

**Billing a visit:** in the Treatment tab, search the catalogue and the details and price
fill in; set "Qty to bill" (e.g. 21 tablets). "Save and generate bill" builds the visit's
bill from the treatment, and "Save and complete" does the same automatically when
something is charged. An optional fixed fee for every visit (e.g. the consultation fee)
is set in Website > Site settings > "Fee added to every visit bill". On the bill, lines
from the visit are kept in step with the treatment ("Update from visit"); other items,
such as food from the shop, are added below them. Once issued, a bill is not changed.

**Selling:** every sale is an invoice.

- *Counter sale:* Billing > New sale. Pick a client, type a name and phone, or leave both
  blank for an anonymous sale. No appointment is needed.
- *Visit bill:* "Bill" in the queue, or "Create bill" on the visit page, starts a bill
  for the pet's owner linked to that visit.

Add items by searching products and services (their price fills in) or by typing a
description and price. A bill is a **draft** until you **issue** it: issuing takes the
items out of stock (refusing if there isn't enough), gives the invoice its number and
locks it. Take one or more payments (cash, card, eSewa, Khalti, Fonepay, bank) until it
is **paid**, or choose "Paid now by" when issuing to issue and take the full amount at once. An issued invoice is never deleted; cancelling it puts its items back in
stock. Print the invoice from its page.

Set the hospital's PAN/VAT number, default VAT rate and invoice footer under
**Website > Site settings**.

**Online shop:** products marked "Show in the online shop", in categories shown online,
appear at `/shop/` with their price. Visitors order by WhatsApp or phone and pick up at
the hospital; there is no online payment.

By default Veterinarians and Receptionists can bill and issue invoices, Receptionists
can also take payments, and only Administrators can adjust stock or cancel invoices.

## Branches

The hospital can work from several branches under one website and one dashboard
(Staff > Branches). Owners, pets, the catalogue and staff accounts are shared by all
branches; **visits, bills, stock and messages belong to a branch**.

- **Who works where:** on each staff user, tick their branches and a default branch, or
  tick "All branches" for owners and managers. With only one branch nothing needs choosing.
- **Switching:** the branch button at the top of the dashboard changes the branch being
  worked in. People with several branches can also choose "All my branches" to see
  everything together; adding a visit or a sale then asks which branch it is for.
- **Queue and bookings:** each branch has its own queue and daily tokens. Walk-ins get a
  triage level (emergency, urgent, routine); emergencies go to the top of the queue, and
  the **Triage board** shows the queue as columns. Visits booked for a later day can have a
  time, and **Clinic > Bookings** shows the week.
- **Stock:** each branch has its own stock count and low-stock warnings. Stock is moved
  with **Shop > Stock transfers**: a transfer leaves the sending branch when sent and
  arrives when the receiving branch marks it received (or goes back if cancelled).
- **Prices:** everything sells at the hospital price unless a branch has its own price
  (Shop > Branch prices). **Sync prices** resets a branch to the hospital prices, copies
  one branch's prices to another, or makes a branch's prices the new hospital prices.
- **Bills:** each branch numbers its own bills (`INV-CODE-2026-00001`) and can have its
  own PAN/VAT number, VAT rate, invoice footer and visit fee; blank values use the ones in
  Site settings.
- **Website:** with more than one open branch, a Branches page and menu link appear, the
  contact form asks which branch, and product pages show which branches have it in stock.

## Clinical records

- **SOAP:** the visit tabs follow Subjective (History), Objective (Examination), and
  Assessment & Plan (Diagnosis & treatment); the printed summary uses the same headings.
- **Treatment templates** (Clinic setup): the usual treatment for a condition. In a visit,
  "Use a template" adds all its lines at the branch's prices, and its diagnosis if none is
  written yet.
- **Documents:** lab reports, X-rays, photos and letters are uploaded on the pet's record
  or a visit. They are stored in `private_media/` and only sent to signed-in staff with
  permission; the web server must **not** serve that folder.
- **Vaccination plans** (Clinic setup): schedules such as puppy core vaccines. Put a pet on
  a plan from its record; each dose shows as due, and is ticked off when the vaccine is
  recorded in a visit.

## Messages and reminders

**Inbox > Reminders** lists tomorrow's bookings, vaccinations coming due and planned doses,
with a "Remind" button that opens a message already written from the matching template
(Clinic setup > Message templates), and "Mark reminded" for reminders given by phone.
Messages can also be sent from a client, a visit or an invoice. Every message is kept in
Inbox > Messages sent.

| Channel | Set up with | Without setup |
| --- | --- | --- |
| WhatsApp | `WHATSAPP_MODE=cloud`, `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` (WhatsApp Business Cloud API) | Opens WhatsApp with the message typed in; staff press send |
| SMS | `SMS_PROVIDER=sparrow` with `SPARROW_SMS_TOKEN` and `SPARROW_SMS_FROM`, or `SMS_PROVIDER=aakash` with `AAKASH_SMS_TOKEN` | Saved in the log only |
| Email | Django's `EMAIL_*` settings | Printed on the console in development |

WhatsApp's Cloud API only delivers free-form text within 24 hours of the owner's last
message; outside that window Meta requires approved templates, so the default link mode is
the practical choice for reminders.

## Reports and activity log

**Billing > Reports** shows sales, payments by method, unpaid balances, visits, each vet's
visits and billed amounts, the best-selling services and products, and stock value, for
any period and for the current branch or all of them. Each table can be downloaded as CSV.
Veterinarians and Administrators see reports; money figures need permission to view
invoices.

**Staff > Activity log** (Administrators) records who added, changed or deleted what,
with the old and new values, and every sign-in and failed sign-in. Passwords are never
stored in it.

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
| `PRIVATE_MEDIA_ROOT` | Where pet documents are stored. Defaults to `private_media/` in the project. |
| `SMS_PROVIDER`, `WHATSAPP_MODE` and their tokens | Messaging; see "Messages and reminders". |

Then run `python manage.py migrate` and `python manage.py collectstatic`, and have
the web server serve `staticfiles/` and `media/`. Do not map `private_media/` to any URL.
