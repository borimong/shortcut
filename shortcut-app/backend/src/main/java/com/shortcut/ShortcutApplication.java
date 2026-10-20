package com.shortcut;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ShortcutApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShortcutApplication.class, args);
    }
}
