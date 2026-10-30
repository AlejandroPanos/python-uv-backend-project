-- Run this script in pgAdmin's Query Tool while connected to the target database.
-- Create the database itself separately, then run this script to create its tables.
-- UUIDs and enum/color defaults declared in the ORM are client-side defaults;
-- inserts made directly in SQL must provide those values.

CREATE TYPE role_enum AS ENUM ('owner', 'maintainer', 'reporter');
CREATE TYPE status_enum AS ENUM ('open', 'in_progress', 'resolved', 'closed');
CREATE TYPE priority_enum AS ENUM ('low', 'medium', 'high', 'urgent');

CREATE TABLE "user" (
	id UUID NOT NULL,
	email VARCHAR(320) NOT NULL,
	hashed_password VARCHAR(1024) NOT NULL,
	is_active BOOLEAN NOT NULL,
	is_superuser BOOLEAN NOT NULL,
	is_verified BOOLEAN NOT NULL,
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_user_email ON "user" (email);

CREATE TABLE projects (
	id UUID NOT NULL,
	owner_id UUID NOT NULL,
	name VARCHAR(120) NOT NULL,
	description VARCHAR(500),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY (owner_id) REFERENCES "user" (id) ON DELETE RESTRICT
);

CREATE TABLE project_members (
	project_id UUID NOT NULL,
	user_id UUID NOT NULL,
	role role_enum NOT NULL,
	joined_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (project_id, user_id),
	FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
	FOREIGN KEY (user_id) REFERENCES "user" (id) ON DELETE CASCADE
);

CREATE TABLE issues (
	id UUID NOT NULL,
	project_id UUID NOT NULL,
	reporter_id UUID NOT NULL,
	assignee_id UUID,
	title VARCHAR(200) NOT NULL,
	body TEXT,
	status status_enum NOT NULL,
	priority priority_enum NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE RESTRICT,
	FOREIGN KEY (reporter_id) REFERENCES "user" (id) ON DELETE RESTRICT,
	FOREIGN KEY (assignee_id) REFERENCES "user" (id) ON DELETE SET NULL
);

CREATE TABLE labels (
	id UUID NOT NULL,
	project_id UUID NOT NULL,
	name VARCHAR(50) NOT NULL,
	color VARCHAR(7) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_labels_project_id_name UNIQUE (project_id, name),
	FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
);

CREATE TABLE comments (
	id UUID NOT NULL,
	issue_id UUID NOT NULL,
	author_id UUID NOT NULL,
	body TEXT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY (issue_id) REFERENCES issues (id) ON DELETE CASCADE,
	FOREIGN KEY (author_id) REFERENCES "user" (id) ON DELETE RESTRICT
);

CREATE TABLE issue_labels (
	issue_id UUID NOT NULL,
	label_id UUID NOT NULL,
	PRIMARY KEY (issue_id, label_id),
	FOREIGN KEY (issue_id) REFERENCES issues (id) ON DELETE CASCADE,
	FOREIGN KEY (label_id) REFERENCES labels (id) ON DELETE CASCADE
);
