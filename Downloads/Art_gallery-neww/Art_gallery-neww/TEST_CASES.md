# Art Gallery – Test Cases & Results

## Project: Art Gallery Web Application
## Technology Stack: Next.js 16, React 19, MySQL 8, TailwindCSS 4
## Date: April 2026

---

## 1. Database Connectivity Tests

| TC ID | Test Case | Input | Expected Output | Actual Output | Status |
|-------|-----------|-------|-----------------|---------------|--------|
| DB-01 | Database connection test | GET `/api/test` | `{ message: "Database connected successfully" }` | `{ message: "Database connected successfully" }` | ✅ PASS |
| DB-02 | Fetch all artists | GET `/api/artists` | Array of artist objects with `artist_id`, `name`, `slug`, `country`, `biography`, `profile_image` | Returns array of 10 artists | ✅ PASS |
| DB-03 | Fetch all categories | GET `/api/categories` | Array of 12 category objects with `category_id`, `name`, `slug`, `description` | Returns 12 categories | ✅ PASS |
| DB-04 | Fetch all artworks | GET `/api/artworks` | Array of artwork objects | Returns array of artworks | ✅ PASS |
| DB-05 | Fetch artworks by artist | GET `/api/artworks?artist_id=1` | Only artworks belonging to artist_id 1 | Returns Leonardo's artworks only | ✅ PASS |
| DB-06 | Fetch world arts with countries | GET `/api/world_arts` | Array with country names joined | Returns arts grouped by country | ✅ PASS |

---

## 2. Authentication Tests (Viewer)

| TC ID | Test Case | Input | Expected Output | Actual Output | Status |
|-------|-----------|-------|-----------------|---------------|--------|
| AV-01 | Register viewer – valid | POST `/api/auth/register-viewer` with `{ name, username, email }` | `{ message: "Registration successful" }` | Registration successful | ✅ PASS |
| AV-02 | Register viewer – duplicate email | POST with existing email | `{ error: "Email already registered." }` + Status 400 | Error returned correctly | ✅ PASS |
| AV-03 | Register viewer – duplicate username | POST with existing username | `{ error: "Username already taken..." }` + Status 400 | Error returned correctly | ✅ PASS |
| AV-04 | Register viewer – invalid username format | POST with `username: "AB"` | `{ error: "Username must be 3-30 characters..." }` + Status 400 | Validation error returned | ✅ PASS |
| AV-05 | Register viewer – missing fields | POST with `{}` | `{ error: "Name, username, and email are required" }` + Status 400 | Error returned | ✅ PASS |
| AV-06 | Login viewer – valid email | POST `/api/auth/login-viewer` with valid email | User data (`user_id`, `name`, `email`, `is_admin`) | User data returned | ✅ PASS |
| AV-07 | Login viewer – invalid email | POST with non-existent email | Status 401 + error message | Error returned properly | ✅ PASS |
| AV-08 | Login viewer – empty email | POST with `{ email: "" }` | Status 400 + "Email is required" | Validation error | ✅ PASS |

---

## 3. Authentication Tests (Artist)

| TC ID | Test Case | Input | Expected Output | Actual Output | Status |
|-------|-----------|-------|-----------------|---------------|--------|
| AA-01 | Register artist – valid | POST `/api/auth/register-artist` with full data | `{ message, artist_id, slug }` | Artist created with auto-generated slug | ✅ PASS |
| AA-02 | Register artist – duplicate email | POST with existing email | Status 400 + error | Error returned | ✅ PASS |
| AA-03 | Login artist – valid | POST `/api/auth/login-artist` with artist email | `{ artist_id, name, slug }` | Artist data returned | ✅ PASS |
| AA-04 | Login artist – non-artist email | POST with viewer email | Status 404 + "No artist found" | Error returned | ✅ PASS |
| AA-05 | Update artist profile | PUT `/api/auth/update-artist` with `{ artist_id, name, biography }` | `{ message: "Profile updated..." }` | Profile updated + slug regenerated | ✅ PASS |
| AA-06 | Update artist – no fields | PUT with only `{ artist_id }` | Status 400 + "No fields to update" | Validation error | ✅ PASS |

---

## 4. Artwork CRUD Tests

| TC ID | Test Case | Input | Expected Output | Actual Output | Status |
|-------|-----------|-------|-----------------|---------------|--------|
| AW-01 | Upload artwork | POST `/api/artworks/upload` with full data | `{ message, artwork_id }` | Artwork created | ✅ PASS |
| AW-02 | Upload artwork – missing fields | POST with `{ artist_id }` only | Status 400 + "Missing required fields" | Validation error | ✅ PASS |
| AW-03 | Delete own artwork | DELETE `/api/artworks/delete` with `{ artist_id, artwork_id }` | `{ message: "Artwork deleted..." }` | Artwork removed | ✅ PASS |
| AW-04 | Delete other's artwork | DELETE with wrong `artist_id` | Status 403 + "Artwork not found or you don't own it" | Authorization denied | ✅ PASS |
| AW-05 | Buy artwork | POST `/api/artworks/buy` with `{ artwork_id, buyer_name, address }` | `{ message: "Purchase completed..." }` | Artwork marked as sold + order created | ✅ PASS |
| AW-06 | Buy already sold artwork | POST `/api/artworks/buy` for sold artwork | Status 400 + "already been sold" | Duplicate purchase prevented | ✅ PASS |
| AW-07 | Buy artwork – missing buyer info | POST with only `{ artwork_id }` | Status 400 + validation error | Error returned | ✅ PASS |

---

## 5. Wishlist Tests

| TC ID | Test Case | Input | Expected Output | Actual Output | Status |
|-------|-----------|-------|-----------------|---------------|--------|
| WL-01 | Add to wishlist | POST `/api/wishlist` with `{ user_id, artwork_id }` | `{ message: "Added to wishlist" }` | Item added | ✅ PASS |
| WL-02 | Fetch user wishlist | GET `/api/wishlist?user_id=1` | Array of wishlist items with title and image | Returns wishlisted items with JOINed data | ✅ PASS |
| WL-03 | Remove from wishlist | DELETE `/api/wishlist` with `{ user_id, artwork_id }` | `{ message: "Removed from wishlist" }` | Item removed | ✅ PASS |
| WL-04 | Add duplicate to wishlist | POST same item twice | Error (duplicate primary key) | Duplicate prevented | ✅ PASS |

---

## 6. Donation Tests

| TC ID | Test Case | Input | Expected Output | Actual Output | Status |
|-------|-----------|-------|-----------------|---------------|--------|
| DN-01 | Make donation | POST `/api/donations` with `{ artist_id, user_id, amount: 100 }` | `{ message: "Donation Successful!" }` | Donation recorded | ✅ PASS |
| DN-02 | Donation – invalid amount | POST with `{ amount: -10 }` | Status 400 + "Invalid Amount" | Validation error | ✅ PASS |
| DN-03 | Donation – zero amount | POST with `{ amount: 0 }` | Status 400 + "Invalid Amount" | Validation error | ✅ PASS |
| DN-04 | Fetch donation history | GET `/api/donations/history?artist_id=5` | `{ total, history: [...] }` with user names | Returns total + donation list | ✅ PASS |
| DN-05 | Fetch history – no artist_id | GET `/api/donations/history` | Status 400 + "artist_id is required" | Validation error | ✅ PASS |

---

## 7. Review Tests

| TC ID | Test Case | Input | Expected Output | Actual Output | Status |
|-------|-----------|-------|-----------------|---------------|--------|
| RV-01 | Post review | POST `/api/review` with `{ artist_id, user_id, rating: 5, comment }` | `{ message: "Review Added!" }` | Review created | ✅ PASS |
| RV-02 | Fetch reviews for artist | GET `/api/review?artist_id=4` | Array of reviews with `user_name`, `rating`, `comment`, `created_at` | Reviews returned with user names | ✅ PASS |
| RV-03 | Fetch reviews – no artist_id | GET `/api/review` | Empty array `[]` | Returns empty array | ✅ PASS |

---

## 8. Admin Tests

| TC ID | Test Case | Input | Expected Output | Actual Output | Status |
|-------|-----------|-------|-----------------|---------------|--------|
| AD-01 | Check admin – valid admin | POST `/api/auth/check-admin` with admin user_id | `{ isAdmin: true }` | Verified as admin | ✅ PASS |
| AD-02 | Check admin – non-admin | POST with regular user_id | `{ isAdmin: false }` | Access denied correctly | ✅ PASS |
| AD-03 | Fetch all users | GET `/api/admin/users` | Array of users with roles | Users list returned | ✅ PASS |
| AD-04 | Fetch admin stats | GET `/api/admin/stats` | `{ users, artists, artworks, totalDonations, reviews }` | Aggregate stats returned | ✅ PASS |
| AD-05 | Delete user (as admin) | DELETE `/api/admin/delete-user` | Cascading delete of user + related data | User and related data removed | ✅ PASS |
| AD-06 | Delete user – not admin | DELETE with non-admin `admin_id` | Status 403 + "Unauthorized" | Access denied | ✅ PASS |
| AD-07 | Delete self (admin) | DELETE with `admin_id == user_id` | Status 400 + "Cannot delete your own admin account" | Self-deletion prevented | ✅ PASS |
| AD-08 | Delete artwork (as admin) | DELETE `/api/admin/delete-artwork` | Artwork deleted + wishlists cleaned | Artwork removed | ✅ PASS |

---

## 9. Order Management Tests

| TC ID | Test Case | Input | Expected Output | Actual Output | Status |
|-------|-----------|-------|-----------------|---------------|--------|
| ORD-01 | Fetch all orders (admin) | GET `/api/admin/orders` | Array of order objects with JOINed artwork title, price, image, artist name | Returns orders with full details | ✅ PASS |
| ORD-02 | Order created on purchase | POST `/api/artworks/buy` with valid data | New row in `orders` table with `buyer_name`, `shipping_address`, `artwork_id` | Order recorded in DB + artwork marked sold | ✅ PASS |
| ORD-03 | Orders – empty result | GET `/api/admin/orders` when no orders exist | Empty array `[]` | Returns empty array | ✅ PASS |
| ORD-04 | Order – artwork details joined | GET `/api/admin/orders` | Each order includes `artwork_title`, `price`, `image_url`, `artist_name` | All joined fields present | ✅ PASS |

---

## 10. File Upload Tests

| TC ID | Test Case | Input | Expected Output | Actual Output | Status |
|-------|-----------|-------|-----------------|---------------|--------|
| UP-01 | Upload image file | POST `/api/upload` with image FormData | `{ url: "/uploads/timestamp_filename.jpg" }` | File saved + URL returned | ✅ PASS |
| UP-02 | Upload without file | POST with empty FormData | Status 400 + "No valid file found." | Validation error | ✅ PASS |

---

## 11. Frontend UI/UX Tests

| TC ID | Test Case | Expected Result | Actual Result | Status |
|-------|-----------|-----------------|---------------|--------|
| UI-01 | Responsive header – mobile | Hamburger menu appears on small screens | Menu toggles with slide animation | ✅ PASS |
| UI-02 | Responsive header – desktop | Full nav links visible | All links displayed inline | ✅ PASS |
| UI-03 | Header scroll blur | Header gets backdrop blur on scroll | Glass effect applied after 40px scroll | ✅ PASS |
| UI-04 | Login form – email validation | Red border on invalid email after blur | Real-time validation feedback shown | ✅ PASS |
| UI-05 | Auth form – file size validation | Error shown for files >5MB | "File size must be under 5MB" displayed | ✅ PASS |
| UI-06 | Auth form – bio character counter | Shows current/max character count | Counter updates live (0/500) | ✅ PASS |
| UI-07 | 404 page | Visit `/nonexistent` | Custom 404 with "Return to Gallery" link | Animated 404 page shown | ✅ PASS |
| UI-08 | Wishlist – empty state | View wishlist when empty | Animated empty state with CTA | Animation + "Explore Art" button | ✅ PASS |
| UI-09 | Wishlist – not logged in | View wishlist without login | Sign-in prompt shown | "Sign In" CTA displayed | ✅ PASS |
| UI-10 | World page – responsive | View on mobile | Grid adjusts (1 → 2 → 3 columns) | Responsive breakpoints work | ✅ PASS |
| UI-11 | Vibes page – loading skeleton | Initial page load | Spinner shown until data loads | Loading spinner displayed | ✅ PASS |
| UI-12 | Dashboard – upload success | Upload artwork successfully | Green success banner appears | Success message shown for 3 seconds | ✅ PASS |
| UI-13 | Dashboard – delete artwork | Click delete + confirm | Artwork removed from list | Artwork removed with confirmation | ✅ PASS |
| UI-14 | Admin panel – search | Type in search box | Tables filter in real-time | Users/artworks filtered by query | ✅ PASS |
| UI-15 | Footer visibility | Scroll to bottom on any page | Footer with links + social icons visible | 4-column footer rendered | ✅ PASS |
| UI-16 | Artist profile page | Visit `/artists/leonardo-da-vinci` | Full profile with artworks, donations, reviews | All sections render correctly | ✅ PASS |
| UI-17 | Smooth scrolling | Click anchor links | Page scrolls smoothly | CSS scroll-behavior: smooth active | ✅ PASS |
| UI-18 | Hero section – animated entrance | Page load on home page | Title, subtitle, and CTAs animate in sequentially | Staggered fade-in + slide-up animations | ✅ PASS |
| UI-19 | Hero section – responsive text | View hero on mobile vs desktop | Text scales from 5xl to 9xl based on breakpoint | Responsive text sizing works | ✅ PASS |
| UI-20 | Hero section – CTA buttons | Click "Explore Gallery" and "Artist Portal" | Navigate to /world and /auth respectively | Both buttons navigate correctly | ✅ PASS |
| UI-21 | Home grid – responsive | View Section Two on mobile | Grid stacks vertically on mobile | Responsive layout works | ✅ PASS |
| UI-22 | World arts section – responsive images | View on tablet/mobile | Images scale proportionally with aspect ratio | No overflow on any screen size | ✅ PASS |
| UI-23 | Artist profile – responsive | Visit artist page on mobile | All sections stack, text scales, no horizontal overflow | Fully responsive layout | ✅ PASS |
| UI-24 | Admin orders tab | Click "Orders" tab in admin panel | Orders table displays with artwork images, buyer info, revenue total | Orders tab renders correctly | ✅ PASS |
| UI-25 | Admin orders – search | Type buyer name in search | Orders filter by buyer name, artwork, or artist | Real-time search filtering works | ✅ PASS |

---

## 12. Integration / End-to-End Tests

| TC ID | Test Case | Flow | Expected Result | Status |
|-------|-----------|------|-----------------|--------|
| E2E-01 | Full viewer journey | Register → Login → Browse → Wishlist → Donate → Review | All steps complete without errors | ✅ PASS |
| E2E-02 | Full artist journey | Register → Login → Upload artwork → Edit profile → View donations | All steps complete without errors | ✅ PASS |
| E2E-03 | Purchase flow | Browse artist → Select artwork → Checkout → Confirm | Artwork marked sold, order recorded | ✅ PASS |
| E2E-04 | Admin management | Login as admin → View stats → Search users → Delete artwork | All admin functions work | ✅ PASS |
| E2E-05 | Admin order tracking | Login as admin → Navigate to Orders tab → View all purchases → Search by buyer | Orders displayed with full details + revenue summary | ✅ PASS |

---

## Summary

| Category | Total Tests | Passed | Failed |
|----------|:-----------:|:------:|:------:|
| Database Connectivity | 6 | 6 | 0 |
| Viewer Authentication | 8 | 8 | 0 |
| Artist Authentication | 6 | 6 | 0 |
| Artwork CRUD | 7 | 7 | 0 |
| Wishlist | 4 | 4 | 0 |
| Donations | 5 | 5 | 0 |
| Reviews | 3 | 3 | 0 |
| Admin | 8 | 8 | 0 |
| Order Management | 4 | 4 | 0 |
| File Upload | 2 | 2 | 0 |
| Frontend UI/UX | 25 | 25 | 0 |
| End-to-End Integration | 5 | 5 | 0 |
| **TOTAL** | **83** | **83** | **0** |

> **All 83 test cases passed successfully.** The application is fully functional, error-free, and meets all project requirements across database connectivity, authentication, CRUD operations, admin management, order tracking, responsive design, and end-to-end user workflows.
