# Welcome to CleanSight
Created by Navya, Sireesha, Arthur, and Aurika

**Inspiration and Ideation:**
Hospitals are meant to aid recovery and the healing process, but preventable infections can still occur due to gaps in sanitation compliance. A single missed surface in a patient room can allow pathogens to spread, putting vulnerable patients at serious risk.

As a team, we were struck by how much hospital cleaning still relies on manual checklists and trust-based reporting. While healthcare technology has advanced rapidly, sanitation monitoring has fallen behind. It often lacks real-time accountability and data visibility.

We asked ourselves a simple question: What if hospital cleaning could be tracked, verified, and optimized like any other critical system? That question became the foundation of our platform and we let it guide our project.

We knew we wanted to create a project utilizing web-cam technology in hospital and medical hygeine related topics. Upon brainstorming, we realized when someone cleans a service, there is no way to know if someone had thoroughly cleaned it without missing a spot, as there is a lot of room for human error. Therefore, CleanSight would help reduce that error and make cleaning more accurate.

**What CleanSight does:**
CleanSight is a data-driven sanitation intelligence platform designed to improve hospital cleaning compliance and reduce preventable infection risk.

Our platform provides many different vital features. It includes real-time cleaning tracking. This logs sanitation activity by room, and time. It also features a compliance analytics dashboard. This visualizes cleaning frequency, missed areas, and high-risk gaps. We also have a risk flagging system, which identifies areas that fall below cleaning thresholds. Additionally, we have performance insights to generate reports and improve accountability and operational efficiency. To summarize, all the variables that we collect include session id, quality score, coverage percept, high and low touch percent, overwipe ratio and hotspots, uniformity, surface type, room id, cleaner id, and start and end time.

From an administrative view, this gives hospital leadership measurable sanitation data for oversight and quality assurance. Instead of relying solely on manual verification, we transform sanitation into actionable, trackable data.

**How we built it:**
We developed the CleanSight frontend using HTML 5 for structure and CSS for inline styling. We also used Vanilla Javascript to allow adding and switching between tabs and retrieved information from the backend via Fetch API.

For the backend, we used Fast API for the core web framework and Uvicorn to run it because it allows for hot reload during development. Other pieces we used include SQLAlchemy for ORM, Pydantic for request and response schema validation, and python-dotenv for managing environment variables and API Keys. For the Data and Analytics section, we used Javascript, JSON, LocalStorage, React, and FetchAPI to create the heatmap and data analysis provided there.

For the database, we used SQLite and Snowflake. SQLite handles local storage of cleaning sessions, grid data, and computed metrics via SQLAlchemy. Snowflake serves as the cloud data warehouse for persistent, scalable storage of session summaries across rooms and facilities. The Actian VectorAI DB stores the 202-dimension contamination fingerprints and returns similar sessions by cosine similarity.

For data visualization, we utilized Sphinx AI, OpenCV heatmap overlays, React, and Vanilla JS live dashboard. Sphinx AI powers intelligent search and analytics over cleaning records. We also used it to reason over live-executed DataFrames to produce structured clinical guidance. OpenCV renders the real-time cleaning heatmap directly onto the MJPEG camera stream. The dashboard uses Fetch API polling to display live coverage percentages, session counts, and high-touch zone completion, updating every 2 seconds. React was enabled in order to produce a heatmap, risk overlay, real-time Sphinx stream, and similar-session panel. The Vultr flask orchestrates analysis, embedding, and streaming.

For our cloud infrastructure, we used Vultr Cloud Compute CPU Instance. The FastAPI backend and all real-time computer vision processing runs on a Vultr CPU instance, keeping latency low while enabling remote access across hospital rooms or facilities.

To protect the data and people involved in this, we utilized SafetyKit. This allowed us to anonymize the identities of sanitation staff by not storing raw camera frames, IP addresses, or any body and face data. This means that only derived metrics like coverage percentage and grid data are ever saved. It also allowed us to require an API key on the session ingest endpoint, which prevents unauthorized users from pushing fake or malicious data into the system.

We focused on creating a system that is lightweight, scalable, and realistic for hospital environments where speed and reliability matter, while not compromising on accuracy.

**Challenges we ran into:**
First, we struggled with designing a reliable tracking mechanism, which included creating a system that accurately logs sanitation activity and required us to think carefully about usability and workflow integration. Cleaning staff need tools that are fast and intuitive, not burdensome. From this, we learned that good health-tech solutions must integrate seamlessly into existing routines rather than disrupt them.

We also had to turn raw data into meaningful insights. Collecting cleaning logs and collecting useful data are entirely different. Therefore, we built analytics that highlight patterns such as frequently missed surfaces, rooms with inconsistent compliance, and time-based sanitation gaps. This transformed simple logs into decision-making tools for administrators.

Balancing accountability and usability was also a struggle. We wanted to increase transparency without creating a punitive atmosphere. That meant designing a dashboard that promotes improvement rather than blame. We didn't want to accuse or be suspicious of sanitation staff. We learned that technology in healthcare must support people and not intimidate them.

**Impact:**
Hospital-acquired infections affect millions of patients globally each year and result in significant fatalities. Many of these infections are linked to preventable sanitation gaps. By making hospital cleaning measurable, visible, and data-driven, our platform helps reduce preventable infection transmission, improve patient safety and health, increase operational accountability, and support regulatory compliance, while also lowering long-term healthcare costs. Preventable infections shouldn’t exist in modern healthcare systems. We’re building the infrastructure to reduce them.

Accomplishments that we're proud of:
The accuracy of the real-time hand tracking and surface coverage calculation genuinely surprised us. MediaPipe's landmark detection translated hand movement into heatmap data far more reliably than we expected. Transforming the physical act of sanitation into measureable, queryable act data was harder than it looks, and the the pipeline we built (from raw heatmap coverage percent, quality score, and missed zones) ended up being more robust than anticipated. Building a functional, end-to-end system within 36 hours, with every layer working together, is something we're lowkenuinely proud of.

**What we learned:**
We learned how heatmaps work in practice, and how we can use it ot accumulate hand position data frame by frame, and translate it into a meaningful coverage grid. We also learned how object detection pipelines work under the hood, specifically how YOLO processes frams and why class-based detection failes in niche environments like hospitals, which push us toward a contour-based fallback approach. Implenting depth perception without AR was also an interesting constraint. We learned that we could palm landmark distance as a proxy for the hand size to estimate cleaning radius. On the tools side, integrating Snowflake, Actian, Sphinx, and Vultr withing a 36-hour window taught us a lot about how these platforms fit together in a real data pipeline.

**What's next for CleanSight:**
There are a couple different directions we could go with CleanSight. It would be nice to adapt this to mobile devices and AR, which would provide greater spatial awareness and precision for real hospital environments.

A more ambitious direction would be integrating with modified Meta smart glasses. The glasses would passively record what has been cleaned hands-free, and with a projector or adaptive display output, staff could see missed zones overlaid directly onto the surface in front of them, removing the screen completely. Paired with proper depth perception, which our current setup can't provide, this would make the coverage tracking significantly more accurate. We could achieve depth either through dedicated hardware like AR headsets or by writing a trigonometry-based solution that estimates depth from camera geometry, both of which we would like to explore either way.
