#include <Stepper.h>
#include <DHT.h>


// L298N

#define ENA 9
#define IN1 8
#define IN2 7

#define ENB 10
#define IN3 6
#define IN4 5


// Sensor Ultrasónico

#define TRIG 11
#define ECHO 12


// MQ02

#define MQ2 A0


// DHT22

#define DHTPIN 2
#define DHTTYPE DHT22

DHT dht(DHTPIN, DHTTYPE);


const int pasosPorVuelta = 2048;

Stepper camaraStepper(
  pasosPorVuelta,
  3, A1, 4, A2
);

int velocidadMotores = 150;

unsigned long ultimoEnvio = 0;


void setup() {

  Serial.begin(9600);
  Serial.setTimeout(50);
  // L298N
  pinMode(ENA, OUTPUT);
  pinMode(ENB, OUTPUT);

  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);

  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);

  // SU
  pinMode(TRIG, OUTPUT);
  pinMode(ECHO, INPUT);

  // Stepper
  camaraStepper.setSpeed(10);

  // DHT
  dht.begin();

  detener();

  Serial.println("ROBOT INICIADO");
}


void loop() {

  avanzar();
  delay(3000);

  detener();
  delay(2000);

  retroceder();
  delay(3000);

  detener();
  delay(2000);
}

// Mov

void avanzar() {

  analogWrite(ENA, velocidadMotores);
  analogWrite(ENB, velocidadMotores);

  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);

  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
}


void retroceder() {

  analogWrite(ENA, velocidadMotores);
  analogWrite(ENB, velocidadMotores);

  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);

  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
}


void izquierda() {

  analogWrite(ENA, velocidadMotores);
  analogWrite(ENB, velocidadMotores);

  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);

  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
}


void derecha() {

  analogWrite(ENA, velocidadMotores);
  analogWrite(ENB, velocidadMotores);

  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);

  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
}


void detener() {

  analogWrite(ENA, 0);
  analogWrite(ENB, 0);

  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);

  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
}

// Distancia

long medirDistancia() {

  digitalWrite(TRIG, LOW);
  delayMicroseconds(2);

  digitalWrite(TRIG, HIGH);
  delayMicroseconds(10);

  digitalWrite(TRIG, LOW);

  long duracion = pulseIn(ECHO, HIGH);

  long distancia = duracion * 0.034 / 2;

  return distancia;
}


void leerComandos() {

  if (Serial.available()) {

    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    Serial.print("RECIBIDO: ");
    Serial.println(cmd);

    if (cmd == "F") {
      Serial.println("ADELANTE");
      avanzar();
    }

    else if (cmd == "B") {
      Serial.println("ATRAS");
      retroceder();
    }

    else if (cmd == "L") {
      Serial.println("IZQUIERDA");
      izquierda();
    }

    else if (cmd == "R") {
      Serial.println("DERECHA");
      derecha();
    }

    else if (cmd == "S") {
      Serial.println("STOP");
      detener();
    }

    else if (cmd == "CL") {
      Serial.println("CAMARA IZQUIERDA");
      camaraStepper.step(100);
    }

    else if (cmd == "CR") {
      Serial.println("CAMARA DERECHA");
      camaraStepper.step(-100);
    }

    else {
      Serial.print("COMANDO DESCONOCIDO: ");
      Serial.println(cmd);
    }
  }
}


void enviarSensores() {

  if (millis() - ultimoEnvio > 1000) {

    ultimoEnvio = millis();

    long distancia = medirDistancia();

    int gas = analogRead(MQ2);

    float temperatura = dht.readTemperature();

    float humedad = dht.readHumidity();

    Serial.print("DIST:");
    Serial.println(distancia);

    Serial.print("GAS:");
    Serial.println(gas);

    Serial.print("TEMP:");
    Serial.println(temperatura);

    Serial.print("HUM:");
    Serial.println(humedad);
  }
}
