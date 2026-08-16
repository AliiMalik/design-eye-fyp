"use client";

import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  cn(
    "group relative inline-flex items-center justify-center gap-2 font-medium",
    "transition-all duration-500 ease-[cubic-bezier(0.32,0.72,0,1)]",
    "active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500",
    "focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-canvas)]",
  ),
  {
    variants: {
      variant: {
        primary:
          "bg-indigo-600 text-white shadow-[var(--shadow-glow)] hover:bg-indigo-500",
        navy: "bg-navy-900 text-white hover:bg-navy-800",
        gradient:
          "bg-gradient-to-r from-indigo-600 via-violet-600 to-violet-500 text-white shadow-[var(--shadow-glow)]",
        outline: cn(
          "bg-[var(--color-surface)] text-[var(--color-ink)]",
          "ring-1 ring-[var(--color-hairline-strong)] hover:bg-[var(--color-surface-2)]",
        ),
        ghost: "text-[var(--color-ink-2)] hover:bg-[var(--color-shell)]",
        danger: "bg-danger text-white hover:opacity-90",
      },
      size: {
        sm: "h-9 rounded-full px-4 text-[13px]",
        md: "h-11 rounded-full px-6 text-sm",
        lg: "h-14 rounded-full px-8 text-base",
        icon: "h-10 w-10 rounded-full",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  /**
   * Trailing glyph. It is never naked next to the label -- it sits in its own
   * circular well, flush with the button's right inner padding, and shifts
   * diagonally on hover to create internal kinetic tension.
   */
  trailingIcon?: React.ReactNode;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, trailingIcon, children, ...props }, ref) => {
    const classes = cn(
      buttonVariants({ variant, size }),
      trailingIcon && size !== "icon" && "pr-1.5",
      className,
    );

    const icon =
      trailingIcon && size !== "icon" ? (
        <span
          className={cn(
            "ml-1 flex items-center justify-center rounded-full",
            "bg-white/15 dark:bg-white/10",
            "transition-transform duration-500 ease-[cubic-bezier(0.32,0.72,0,1)]",
            "group-hover:translate-x-1 group-hover:-translate-y-[1px] group-hover:scale-105",
            size === "lg" ? "h-10 w-10" : size === "sm" ? "h-6 w-6" : "h-8 w-8",
            (variant === "outline" || variant === "ghost") && "bg-[var(--color-shell)]",
          )}
          aria-hidden
        >
          {trailingIcon}
        </span>
      ) : null;

    // Slot clones its single child, so that child must be a real element --
    // never a Fragment, or React warns that Fragment got a className.
    if (asChild) {
      const child = React.Children.only(children) as React.ReactElement<{
        children?: React.ReactNode;
      }>;
      return (
        <Slot ref={ref} className={classes} {...props}>
          {React.cloneElement(
            child,
            undefined,
            <>
              {child.props.children}
              {icon}
            </>,
          )}
        </Slot>
      );
    }

    return (
      <button ref={ref} className={classes} {...props}>
        {children}
        {icon}
      </button>
    );
  },
);
Button.displayName = "Button";
