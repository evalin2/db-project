DROP TABLE nutzer;
DROP TABLE tennisplatz;
DROP TABLE wartunsarbeiter;
DROP TABLE buchung;


CREATE TABLE nutzer (
    nid INT AUTO_INCREMENT PRIMARY KEY,
    vorname VARCHAR(250),
    nachname VARCHAR(250),
    geburtsdatum DATE,
    email VARCHAR(100)
);

CREATE TABLE wartungsarbeiter (
    wid INT AUTO_INCREMENT PRIMARY KEY,
    vorname VARCHAR(250),
    nachname VARCHAR(250),
    geburtsdatum DATE
);

CREATE TABLE tennisplatz (
    tid INT AUTO_INCREMENT PRIMARY KEY,
    belag VARCHAR(100),
    tennisanlage VARCHAR(250),
    platznummer VARCHAR(10),
    standort VARCHAR(250),
    wid INT NOT NULL,
    datum_der_wartung DATE,
    FOREIGN KEY (wid) REFERENCES wartungsarbeiter(wid)
);

CREATE TABLE buchung (
    buchungsnummer INT AUTO_INCREMENT PRIMARY KEY,
    nid INT NOT NULL,
    tid INT NOT NULL,
    spieldatum DATE,
    spiellaenge CHAR(2),
    FOREIGN KEY (nid) REFERENCES nutzer(nid),
    FOREIGN KEY (tid) REFERENCES tennisplatz(tid)
);
