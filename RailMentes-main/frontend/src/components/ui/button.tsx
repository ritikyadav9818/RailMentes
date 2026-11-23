import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "../../utils/cn";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-sm font-medium [&_svg]:shrink-0 transition-[color,background-color,border-color,transform,box-shadow] duration-150 active:scale-[0.97] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/70 focus-visible:ring-offset-1 focus-visible:ring-offset-bg disabled:pointer-events-none disabled:opacity-40",
  {
    variants: {
      variant: {
        default: "bg-accent text-bg shadow-[0_0_18px_-4px_rgb(56_189_248_/_0.6)] hover:bg-accent/90",
        outline: "border border-white/10 bg-raised/80 text-text hover:border-accent/60 hover:bg-raised",
        ghost: "text-muted hover:bg-white/[0.07] hover:text-text",
        warn: "border border-warn/50 bg-warn/10 text-warn hover:bg-warn/20",
        danger: "border border-crit/50 bg-crit/10 text-crit hover:bg-crit/20",
      },
      size: {
        sm: "h-7 px-2.5 text-xs",
        md: "h-8 px-3",
        icon: "h-8 w-8",
      },
    },
    defaultVariants: { variant: "outline", size: "md" },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, asChild, ...props }, ref) => {
  const Comp = asChild ? Slot : "button";
  return <Comp ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
});
Button.displayName = "Button";

export { Button };
